from enum import Enum


class NoteState(str, Enum):
    PROCESSING = "processing"
    PREVIEW = "preview"
    EDITING = "editing"
    SAVING = "saving"
