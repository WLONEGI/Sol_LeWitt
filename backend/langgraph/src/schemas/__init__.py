# Schemasモジュール
from .outputs import (
    TaskStep,
    PlannerOutput,
    SlideContent,
    StorywriterOutput,
    ImagePrompt,
    StructuredImagePrompt,  # v2: Markdown Slide Format
    VisualizerOutput,
    SearchQuery,
    QueryPlannerOutput,
    DataAnalystOutput,
    ReviewOutput,
    ThoughtSignature,
    GenerationConfig,
    ResearchTask,
    ResearchResult,
    ResearchTaskList,
)


from .design import (
    DesignContext,
    ColorScheme,
    FontScheme,
    SlideLayoutInfo,
    LayoutPlaceholder,
    BackgroundInfo,
    LayoutType,
)



__all__ = [
    # Outputs
    "TaskStep",

    "PlannerOutput",
    "SlideContent",
    "StorywriterOutput",
    "ImagePrompt",
    "StructuredImagePrompt",
    "VisualizerOutput",
    "SearchQuery",
    "QueryPlannerOutput",
    "DataAnalystOutput",
    "ReviewOutput",
    "ThoughtSignature",
    "GenerationConfig",
    "ResearchTask",
    "ResearchResult",
    "ResearchTaskList",
    # Design Context
    "DesignContext",
    "ColorScheme",
    "FontScheme",
    "SlideLayoutInfo",
    "LayoutPlaceholder",
    "BackgroundInfo",
    "LayoutType",
]

