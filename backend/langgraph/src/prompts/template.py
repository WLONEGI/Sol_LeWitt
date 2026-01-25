"""
プロンプトテンプレートローダー

Markdownファイルからプロンプトテンプレートを読み込み、
LangChainのPromptTemplateとして利用するためのユーティリティ。
"""
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from langchain_core.prompts import PromptTemplate
from langgraph.prebuilt.chat_agent_executor import AgentState


# プロンプトファイルが格納されているディレクトリ
_PROMPTS_DIR: Path = Path(__file__).parent


def get_prompt_template(prompt_name: str) -> str:
    """
    指定されたプロンプト名のMarkdownファイルを読み込み、
    LangChain用のテンプレート文字列に変換する。

    変換ルール:
    - `{` `}` は `{{` `}}` にエスケープ
    - `<<VAR>>` は `{VAR}` に置換

    Args:
        prompt_name: プロンプトファイル名（拡張子なし）

    Returns:
        LangChain PromptTemplate用の文字列

    Raises:
        FileNotFoundError: 指定されたプロンプトファイルが存在しない場合
    """
    filepath: Path = _PROMPTS_DIR / f"{prompt_name}.md"
    template: str = filepath.read_text(encoding="utf-8")

    # LangChain用にエスケープ
    template = template.replace("{", "{{").replace("}", "}}")

    # カスタム変数記法 `<<VAR>>` を `{VAR}` に置換
    template = re.sub(r"<<([^>>]+)>>", r"{\1}", template)

    return template


def load_prompt_markdown(prompt_name: str) -> str:
    """
    プロンプトMarkdownファイルを変数置換なしでプレーンテキストとして読み込む。

    Args:
        prompt_name: プロンプトファイル名（拡張子なし）

    Returns:
        ファイルの内容（文字列）

    Raises:
        FileNotFoundError: 指定されたプロンプトファイルが存在しない場合
    """
    filepath: Path = _PROMPTS_DIR / f"{prompt_name}.md"
    return filepath.read_text(encoding="utf-8")


def apply_prompt_template(prompt_name: str, state: AgentState) -> list[dict[str, Any]]:
    """
    プロンプトテンプレートを読み込み、状態変数を適用してシステムメッセージを生成する。

    Args:
        prompt_name: プロンプトファイル名（拡張子なし）
        state: LangGraphのAgentState（メッセージ履歴と変数を含む）

    Returns:
        システムメッセージとメッセージ履歴を含むリスト
    """
    system_prompt: str = PromptTemplate(
        input_variables=["CURRENT_TIME"],
        template=get_prompt_template(prompt_name),
    ).format(
        CURRENT_TIME=datetime.now().strftime("%a %b %d %Y %H:%M:%S %z"),
        **state
    )
    return [{"role": "system", "content": system_prompt}] + state["messages"]
