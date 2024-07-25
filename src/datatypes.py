from __future__ import annotations

from enum import Enum, auto
from typing import Optional, List, Dict

from pydantic import BaseModel


def get_base_actions():
    return [
        Action.INCOME,
        Action.FOREIGN_AID,
        Action.COUP,
        Action.TAX,
        Action.ASSASSINATE,
        Action.EXCHANGE,
        Action.STEAL,
    ]


def get_challenge_actions():
    return [
        Action.CHALLENGE,
        Action.NO_CHALLENGE,
    ]


def get_counter_actions():
    return [
        Action.COUNTER,
        Action.NO_COUNTER,
    ]


def get_discard_actions():
    return [
        Action.DISCARD,
        Action.DISCARD_TWO,
    ]


class Action(Enum):
    INCOME = auto()
    FOREIGN_AID = auto()
    COUP = auto()
    TAX = auto()
    ASSASSINATE = auto()
    EXCHANGE = auto()
    STEAL = auto()
    CHALLENGE = auto()
    NO_CHALLENGE = auto()
    COUNTER = auto()
    NO_COUNTER = auto()
    DISCARD = auto()  # Removes 1 card
    DISCARD_TWO = auto()  # Removes 2 cards


def get_all_actions() -> List[str]:
    return list(Action.__members__.keys())


class Card(Enum):
    DUKE = auto()
    ASSASSIN = auto()
    CAPTAIN = auto()
    AMBASSADOR = auto()
    CONTESSA = auto()


CARD_FOREGROUND_COLOR_MAP: Dict[Card, str] = {
    Card.CONTESSA: "#6d191c",
    Card.DUKE: "#632d55",
    Card.ASSASSIN: "#0f1011",
    Card.CAPTAIN: "#104894",
    Card.AMBASSADOR: "#a59533",
}

CARD_BACKGROUND_COLOR_MAP: Dict[Card, str] = {
    Card.CONTESSA: "#000000",
    Card.DUKE: "#000000",
    Card.ASSASSIN: "#A9A9A9",
    Card.CAPTAIN: "#A9A9A9",
    Card.AMBASSADOR: "#000000",
}


def get_all_cards() -> List[str]:
    return list(Card.__members__.keys())


class MessageType(Enum):
    SPEECH = auto()
    GAME_EVENT = auto()
    ACTION = auto()
    TASK = auto()
    TASK_COMPLETE = auto()  # game tells agent that task is complete


class MessageFactory:
    @staticmethod
    def create_message(message_type: MessageType, **kwargs):
        if message_type == MessageType.SPEECH:
            return SpeechMessage(**kwargs)
        elif message_type == MessageType.GAME_EVENT:
            return GameEventMessage(**kwargs)
        elif message_type == MessageType.ACTION:
            return ActionMessage(**kwargs)
        elif message_type == MessageType.TASK:
            return TaskMessage(**kwargs)
        elif message_type == MessageType.TASK_COMPLETE:
            return TaskMessage(**kwargs)
        else:
            raise ValueError(f"Invalid message type: {message_type}")


class Message(BaseModel):
    message_type: MessageType


class SpeechMessage(Message):
    # Represents a message that an Agent wants to say
    content: str
    sender: str
    message_type: MessageType = MessageType.SPEECH


class GameEventMessage(Message):
    # Instructs an agent of events occurring in the game or errors
    content: str
    message_type: MessageType = MessageType.GAME_EVENT


class ActionMessage(Message):
    action: Action
    sender: str
    target: Optional[str] = None
    cards: Optional[List[Card]] = None
    message_type: MessageType = MessageType.ACTION

    def __str__(self) -> str:
        if self.target:
            return f"{self.action} {self.target}"
        if self.cards:
            cards_str = ", ".join([str(card) for card in self.cards])
            return f"{self.action} {cards_str}"
        return str(self.action)


class TaskMessage(Message):
    # Appends a task to the Agent's task list
    content: str
    expected_actions: Optional[List[Action]] = None
    message_type: MessageType = MessageType.TASK

