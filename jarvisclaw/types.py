"""Response types for JarvisClaw SDK."""
from dataclasses import dataclass, field


@dataclass
class ChatResponse:
    """Response from chat/chat_completion."""
    content: str
    model: str = ""
    id: str = ""
    usage: dict = field(default_factory=dict)
    raw: dict = field(default_factory=dict)


@dataclass
class ImageResponse:
    """Response from image_generate."""
    url: str = ""
    b64_json: str = ""
    revised_prompt: str = ""
    raw: dict = field(default_factory=dict)


@dataclass
class VideoJob:
    """Response from video_generate."""
    id: str = ""
    status: str = ""
    url: str = ""
    raw: dict = field(default_factory=dict)


@dataclass
class AudioResponse:
    """Response from audio_speech."""
    content: bytes = b""
    content_type: str = "audio/mpeg"


@dataclass
class SearchResult:
    """Single search result."""
    title: str = ""
    url: str = ""
    snippet: str = ""


@dataclass
class Model:
    """Model info from list_models."""
    id: str = ""
    object: str = "model"
    owned_by: str = ""
