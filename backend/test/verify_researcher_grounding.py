import asyncio
import logging
import sys
import os

# プロジェクトルートをパスに追加
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.core.workflow.nodes.researcher import research_worker_node
from src.shared.schemas import ResearchTask
from langchain_core.runnables import RunnableConfig

from unittest.mock import patch

# ログ設定
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def main():
    print("=== Researcher Grounding Verification ===")
    
    # adispatch_custom_event をパッチして、スタンドアロン実行時のエラーを回避
    with patch("langchain_core.callbacks.manager.adispatch_custom_event"):
        # 最近の出来事に関するタスクを作成
        task = ResearchTask(
            id=1,
            perspective="今日の東京の天気と、現在開催中の主要なイベント",
            query_hints=["東京 天気 2026年1月31日", "東京 ニュース 今日"],
            priority="high",
            expected_output="今日の東京の天気予報と、現在東京で行われている主要なニュース・イベントを3つ以上挙げてください。"
        )
        
        state = {
            "task": task
        }
        
        config = RunnableConfig(
            configurable={"thread_id": "test_thread"}
        )
        
        print(f"Task: {task.perspective}")
        print("Executing research_worker_node...")
        
        try:
            # ノードを実行
            result = await research_worker_node(state, config)
            
            # 結果を表示
            research_results = result.get("internal_research_results", [])
            if research_results:
                report = research_results[0].report
                print("\n--- Research Report ---")
                print(report)
                print("-----------------------\n")
                
                # グラウンディングが行われたかどうかの確認（ヒント：新しい情報が含まれているか）
                if "2026" in report or "今日" in report or "イベント" in report or "天気" in report:
                    print("SUCCESS: Research report contains relevant information.")
                else:
                    print("WARNING: Report might not contain specific recent information.")
            else:
                print("ERROR: No research results returned.")
                
        except Exception as e:
            print(f"ERROR during execution: {e}")
            import traceback
            traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())
