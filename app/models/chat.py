from typing import List
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

MAX_FILE_BYTES = 10 * 1024 * 1024
MAX_ATTACHMENTS = 3


class ChatMessageInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    clientMessageId: UUID
    text: str = Field(default="", max_length=5000)
    attachmentIds: List[str] = Field(default_factory=list, max_length=MAX_ATTACHMENTS)

    @field_validator("text", mode="before")
    @classmethod
    def trim_text(cls, value):
        return value.strip() if isinstance(value, str) else value

    @model_validator(mode="after")
    def validate_content(self):
        self.text = self.text.strip()
        if not self.text and not self.attachmentIds:
            raise ValueError("A message needs text or an attachment.")
        if len(set(self.attachmentIds)) != len(self.attachmentIds):
            raise ValueError("Duplicate attachments.")
        return self


class ChatReadInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    lastReadSeq: int = Field(ge=0, strict=True)
