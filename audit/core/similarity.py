"""
核心相似度检索模块（第二阶段重构版）

变更点：
1. 新增 load_cases_from_db() —— 从 AuditRecord 表动态加载历史案例
2. search_similar_cases() 优先从数据库加载，数据库为空时 fallback 到硬编码种子数据
3. 新增 save_case_to_db() —— 将新的审计结果保存为历史案例（闭环学习）
4. 保留 _preprocess_code() 和 TF-IDF + 余弦相似度的核心算法不变

算法选型（与第一阶段一致）：
- TF-IDF 向量化 + 余弦相似度
- 后续阶段可无缝替换为 Sentence-Transformers 或 OpenAI Embedding
"""

import re
import logging
from typing import List, Dict, Optional

import jieba
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

logger = logging.getLogger(__name__)


# ============================================================
# 1. 硬编码种子案例库（作为数据库为空时的 fallback）
# ============================================================
_SEED_CASES: List[Dict[str, str]] = [
    {
        "id": 1,
        "issue_type": "SQL注入",
        "original_code": 'cursor.execute("SELECT * FROM users WHERE id = " + user_id)',
        "suggested_fix": 'cursor.execute("SELECT * FROM users WHERE id = %s", (user_id,))',
        "description": "字符串拼接 SQL 语句导致 SQL 注入风险，应使用参数化查询",
    },
    {
        "id": 2,
        "issue_type": "XSS漏洞",
        "original_code": 'return "<div>" + user_input + "</div>"',
        "suggested_fix": 'from django.utils.html import escape\nreturn "<div>" + escape(user_input) + "</div>"',
        "description": "未对用户输入进行转义，导致跨站脚本攻击（XSS）风险",
    },
    {
        "id": 3,
        "issue_type": "硬编码密钥",
        "original_code": 'SECRET_KEY = "my-super-secret-key-12345"',
        "suggested_fix": 'import os\nSECRET_KEY = os.environ.get("SECRET_KEY")',
        "description": "密钥硬编码在源码中，应从环境变量读取",
    },
    {
        "id": 4,
        "issue_type": "不安全的反序列化",
        "original_code": "data = pickle.loads(user_upload)",
        "suggested_fix": "import json\ndata = json.loads(user_upload)",
        "description": "使用 pickle 反序列化不可信数据可导致远程代码执行",
    },
    {
        "id": 5,
        "issue_type": "空密码校验",
        "original_code": 'if password == "":\n    return False',
        "suggested_fix": 'if not password or len(password) < 8:\n    return False',
        "description": "密码校验过于简单，应增加长度和复杂度检查",
    },
    {
        "id": 6,
        "issue_type": "路径遍历",
        "original_code": 'file = open(user_path, "r")',
        "suggested_fix": 'import os\nsafe_path = os.path.join(BASE_DIR, os.path.basename(user_path))\nfile = open(safe_path, "r")',
        "description": "直接使用用户提供的路径打开文件，存在路径遍历风险",
    },
    {
        "id": 7,
        "issue_type": "不安全的随机数",
        "original_code": "token = random.randint(100000, 999999)",
        "suggested_fix": "import secrets\ntoken = secrets.token_hex(16)",
        "description": "使用 random 模块生成安全令牌，应使用 secrets 模块",
    },
    {
        "id": 8,
        "issue_type": "异常信息泄露",
        "original_code": 'except Exception as e:\n    return str(e)',
        "suggested_fix": 'except Exception as e:\n    logger.error(f"内部错误: {e}")\n    return "服务器内部错误"',
        "description": "直接将异常信息返回给用户，可能泄露系统内部细节",
    },
]


# ============================================================
# 2. 数据库加载函数
# ============================================================
def load_cases_from_db() -> List[Dict[str, str]]:
    """
    从 AuditRecord 表动态加载历史案例

    只加载「已修复」的记录作为相似度匹配的候选案例，
    因为已修复的案例才有参考价值。

    Returns:
        案例列表，每个元素是 dict，格式与 _SEED_CASES 一致
    """
    try:
        # 延迟导入，避免循环依赖
        from audit.models import AuditRecord

        records = AuditRecord.objects.filter(is_fixed=True).values(
            "id",
            "issue_type",
            "original_code",
            "suggested_fix",
            "description",
        )

        cases = []
        for r in records:
            if r["original_code"]:  # 跳过空代码片段
                cases.append({
                    "id": r["id"],
                    "issue_type": r["issue_type"],
                    "original_code": r["original_code"],
                    "suggested_fix": r["suggested_fix"] or "",
                    "description": r["description"] or "",
                })

        logger.info(f"从数据库加载了 {len(cases)} 条历史案例")
        return cases

    except Exception as e:
        # 数据库未迁移 / 表不存在等场景，静默降级
        logger.warning(f"数据库加载失败，将使用种子数据: {e}")
        return []


def save_case_to_db(
    issue_type: str,
    original_code: str,
    suggested_fix: str,
    description: str,
    severity: str = "medium",
    code_file=None,
) -> bool:
    """
    将审计结果保存为新的历史案例，用于后续的相似度匹配（闭环学习）

    Args:
        issue_type    : 问题类型
        original_code : 原始代码片段
        suggested_fix : 修复建议
        description   : 问题描述
        severity      : 严重程度
        code_file     : 关联的 CodeFile 对象（可选）

    Returns:
        是否保存成功
    """
    try:
        from audit.models import AuditRecord, CodeFile

        # 如果没有传入 code_file，获取或创建一个占位记录
        if code_file is None:
            code_file, _ = CodeFile.objects.get_or_create(
                file_path="unknown",
                defaults={"content": "", "language": "Python"},
            )

        AuditRecord.objects.create(
            code_file=code_file,
            issue_type=issue_type,
            description=description,
            severity=severity,
            original_code=original_code,
            suggested_fix=suggested_fix,
            is_fixed=True,  # 标记为已修复，作为后续匹配的候选案例
        )

        logger.info(f"已保存新的历史案例: {issue_type}")
        return True

    except Exception as e:
        logger.warning(f"保存历史案例失败: {e}")
        return False


# ============================================================
# 3. 代码文本预处理（与第一阶段一致）
# ============================================================
def _preprocess_code(code_text: str) -> str:
    """
    对代码文本进行预处理，为 TF-IDF 向量化做准备

    处理步骤：
    ① 移除多余空白符
    ② 移除 Python 风格注释
    ③ 使用 jieba 分词
    ④ 过滤纯标点和无意义 token
    """
    text = re.sub(r"\s+", " ", code_text.strip())
    text = re.sub(r"#.*?(?=\n|$)", "", text)
    tokens = jieba.lcut(text)
    filtered_tokens = [
        t.strip()
        for t in tokens
        if len(t.strip()) >= 1 and not re.match(r"^[\s\W]+$", t)
    ]
    return " ".join(filtered_tokens)


# ============================================================
# 4. 核心检索函数（第二阶段：优先从数据库加载）
# ============================================================
def search_similar_cases(
    code_snippet: str,
    top_k: int = 3,
    use_db: bool = True,
) -> List[Dict[str, object]]:
    """
    在历史案例库中检索与给定代码片段最相似的修复案例

    与第一阶段的区别：
    - 优先从 AuditRecord 表加载历史案例（use_db=True）
    - 数据库为空时自动 fallback 到硬编码种子数据
    - 保留 TF-IDF + 余弦相似度的核心算法

    Args:
        code_snippet : 待检索的代码片段字符串
        top_k        : 返回最相似的前 K 个结果，默认为 3
        use_db       : 是否从数据库加载（设为 False 则只用种子数据）

    Returns:
        一个列表，每个元素是字典，包含 case_id, issue_type, description,
        original_code, suggested_fix, similarity
    """
    # ----------------------------------------------------------
    # 步骤 1：加载历史案例
    # ----------------------------------------------------------
    if use_db:
        cases = load_cases_from_db()
        if not cases:
            logger.info("数据库无案例，使用种子数据")
            cases = _SEED_CASES
    else:
        cases = _SEED_CASES

    if not cases:
        return []

    # ----------------------------------------------------------
    # 步骤 2：预处理
    # ----------------------------------------------------------
    query_processed = _preprocess_code(code_snippet)
    corpus = [_preprocess_code(c["original_code"]) for c in cases]
    all_texts = corpus + [query_processed]

    # ----------------------------------------------------------
    # 步骤 3：TF-IDF 向量化
    # ----------------------------------------------------------
    vectorizer = TfidfVectorizer()
    tfidf_matrix = vectorizer.fit_transform(all_texts)

    # ----------------------------------------------------------
    # 步骤 4：余弦相似度
    # ----------------------------------------------------------
    query_vector = tfidf_matrix[-1]
    document_vectors = tfidf_matrix[:-1]
    similarities = cosine_similarity(query_vector, document_vectors).flatten()

    # ----------------------------------------------------------
    # 步骤 5：排序取 Top-K
    # ----------------------------------------------------------
    ranked_indices = similarities.argsort()[::-1][:top_k]

    results = []
    for idx in ranked_indices:
        case = cases[idx]
        score = float(similarities[idx])
        results.append({
            "case_id": case["id"],
            "issue_type": case["issue_type"],
            "description": case["description"],
            "original_code": case["original_code"],
            "suggested_fix": case["suggested_fix"],
            "similarity": round(score, 4),
        })

    return results


# ============================================================
# 5. 独立运行测试
# ============================================================
if __name__ == "__main__":
    test_snippet = '''
    query = "SELECT * FROM products WHERE category = '" + category + "'"
    cursor.execute(query)
    '''

    print("=" * 60)
    print("搜索相似历史修复案例（第二阶段：数据库 + 种子数据）")
    print("=" * 60)
    print(f"输入代码片段:\n{test_snippet}")
    print("-" * 60)

    results = search_similar_cases(test_snippet, top_k=3, use_db=False)

    for i, r in enumerate(results, 1):
        print(f"\n第 {i} 个相似案例（相似度: {r['similarity']:.2%}）")
        print(f"   问题类型: {r['issue_type']}")
        print(f"   问题描述: {r['description']}")
        print(f"   原始代码: {r['original_code']}")
        print(f"   修复建议: {r['suggested_fix']}")
