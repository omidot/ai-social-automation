class VideoError(Exception):
    """Base for all Phase 2A video-stage failures."""

class VideoScriptError(VideoError):
    pass

class CodegenError(VideoError):
    pass

class TTSError(VideoError):
    pass

class AlignError(VideoError):
    pass
