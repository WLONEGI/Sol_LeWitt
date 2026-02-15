import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from langchain_core.messages import SystemMessage
from langchain_core.prompts import PromptTemplate
from langgraph.prebuilt.chat_agent_executor import AgentState

logger = logging.getLogger(__name__)

# プロンプトファイルが格納されているディレクトリ
_PROMPTS_DIR: Path = Path(__file__).parent
_MODE_FALLBACK_BY_PROMPT_AND_PRODUCT: dict[str, dict[str, str]] = {
    "writer": {"comic": "story_framework"},
    "visualizer_prompt": {"comic": "comic_page_render"},
}


def _resolve_specific_prompt_path(
    *,
    prompt_dir: Path,
    product_type: Any,
    mode: Any,
) -> Path | None:
    normalized_product_type = str(product_type).strip() if isinstance(product_type, str) and product_type.strip() else ""
    normalized_mode = str(mode).strip() if isinstance(mode, str) and mode.strip() else ""

    candidates: list[Path] = []
    if normalized_product_type and normalized_mode:
        candidates.append(prompt_dir / normalized_product_type / f"{normalized_mode}.md")
        candidates.append(prompt_dir / f"{normalized_product_type}_{normalized_mode}.md")
    if normalized_mode:
        candidates.append(prompt_dir / f"{normalized_mode}.md")
    if normalized_product_type:
        candidates.append(prompt_dir / f"{normalized_product_type}.md")

    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def _format_prompt_for_langchain(template: str) -> str:
    """
    LangChain用にテンプレート文字列を変換する。
    - `{` `}` は `{{` `}}` にエスケープ
    - `<<VAR>>` は `{VAR}` に置換
    """
    # LangChain用にエスケープ
    template = template.replace("{", "{{").replace("}", "}}")

    # カスタム変数記法 `<<VAR>>` を `{VAR}` に置換
    template = re.sub(r"<<([^>>]+)>>", r"{\1}", template)

    return template


def get_prompt_template(prompt_name: str) -> str:
    """
    [互換性維持用] 指定されたプロンプト名に対応するファイルを読み込み、テンプレート文字列を返す。
    新構造では {prompt_name}/default.md または {prompt_name}/base.md を優先的に探す。
    """
    prompt_dir = _PROMPTS_DIR / prompt_name
    if not prompt_dir.is_dir():
        # 旧構造へのフォールバック（ファイルが直下にある場合）
        filepath = _PROMPTS_DIR / f"{prompt_name}.md"
        if filepath.exists():
            return _format_prompt_for_langchain(filepath.read_text(encoding="utf-8"))
        raise FileNotFoundError(f"Prompt file or directory not found: {prompt_name}")

    # 新構造での優先順位: default.md > base.md
    for filename in ["default.md", "base.md"]:
        filepath = prompt_dir / filename
        if filepath.exists():
            return _format_prompt_for_langchain(filepath.read_text(encoding="utf-8"))

    # 何も見つからない場合はディレクトリ内の最初の .md を返す
    first_md = next(prompt_dir.glob("*.md"), None)
    if first_md:
        return _format_prompt_for_langchain(first_md.read_text(encoding="utf-8"))

    raise FileNotFoundError(f"No .md files found in prompt directory: {prompt_name}")


def load_prompt_markdown(prompt_name: str) -> str:
    """
    [互換性維持用] プロンプトMarkdownファイルを変数置換なしでプレーンテキストとして読み込む。
    """
    prompt_dir = _PROMPTS_DIR / prompt_name
    if not prompt_dir.is_dir():
        filepath = _PROMPTS_DIR / f"{prompt_name}.md"
        if filepath.exists():
            return filepath.read_text(encoding="utf-8")
        raise FileNotFoundError(f"Prompt content not found: {prompt_name}")

    for filename in ["default.md", "base.md"]:
        filepath = prompt_dir / filename
        if filepath.exists():
            return filepath.read_text(encoding="utf-8")

    first_md = next(prompt_dir.glob("*.md"), None)
    if first_md:
        return first_md.read_text(encoding="utf-8")

    raise FileNotFoundError(f"No .md files found in prompt directory: {prompt_name}")


def apply_prompt_template(prompt_name: str, state: AgentState) -> list[Any]:
    """
    プロンプト構成を結合し、状態変数を適用してシステムメッセージを生成する。
    1. {prompt_name}/base.md
    2. mode指定時は mode専用ファイル（優先）:
       - {prompt_name}/{product_type}/{mode}.md
       - {prompt_name}/{product_type}_{mode}.md
       - {prompt_name}/{mode}.md
       mode未指定時は一部プロンプトで product_type ごとの既定 mode を補完する。
    3. mode専用がなければ {prompt_name}/{product_type}.md
    4. どちらもない場合は default.md または既存ファイル
    """
    product_type = state.get("product_type")
    mode = state.get("mode")
    resolved_mode = mode
    if not (isinstance(mode, str) and mode.strip()):
        product_key = str(product_type).strip() if isinstance(product_type, str) else ""
        resolved_mode = _MODE_FALLBACK_BY_PROMPT_AND_PRODUCT.get(prompt_name, {}).get(product_key)
    prompt_dir = _PROMPTS_DIR / prompt_name
    
    parts = []
    
    if prompt_dir.is_dir():
        # 1. Base (共通指示)
        base_path = prompt_dir / "base.md"
        if base_path.exists():
            parts.append(base_path.read_text(encoding="utf-8"))

        # 2. Specific (mode優先、なければproduct_type)
        specific_path = _resolve_specific_prompt_path(
            prompt_dir=prompt_dir,
            product_type=product_type,
            mode=resolved_mode,
        )
        if specific_path is not None:
            parts.append(specific_path.read_text(encoding="utf-8"))
                
        # 3. Fallback (単一指示)
        if not parts:
            default_path = prompt_dir / "default.md"
            if default_path.exists():
                parts.append(default_path.read_text(encoding="utf-8"))
    else:
        # ディレクトリがない場合は旧形式の単一ファイルとして読み込む
        try:
            parts.append(load_prompt_markdown(prompt_name))
        except FileNotFoundError:
            logger.warning(f"Prompt name '{prompt_name}' could not be resolved.")

    if not parts:
        logger.error(f"Failed to load any prompt parts for: {prompt_name}")
        full_content = f"Error: Prompt {prompt_name} not found."
    else:
        full_content = "\n\n".join(parts)

    prompt_state = dict(state)
    if resolved_mode and not (isinstance(prompt_state.get("mode"), str) and str(prompt_state.get("mode")).strip()):
        prompt_state["mode"] = resolved_mode

    system_prompt: str = PromptTemplate(
        input_variables=["CURRENT_TIME"],
        template=_format_prompt_for_langchain(full_content),
    ).format(
        CURRENT_TIME=datetime.now().strftime("%a %b %d %Y %H:%M:%S %z"),
        **prompt_state
    )
    return [SystemMessage(content=system_prompt)] + state.get("messages", [])
