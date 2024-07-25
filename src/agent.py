import asyncio
import random

from typing import List, Any, Optional

from pydantic import BaseModel, Field

from src.datatypes import Message, MessageType, Action, Card, GameEventMessage, SpeechMessage, ActionMessage, TaskMessage
from src.helper import requires_target, get_openai_stream

from src.print_utils import print_text


def map_action_to_output_format(action: Action):
    action_name = str(action.name)

    if requires_target(action):
        return f"{action_name} <target>"

    if action == Action.DISCARD:
        return f"{action_name} <card>"

    if action == Action.DISCARD_TWO:
        return f"{action_name} <card1> <card2>"

    return action_name


def game_explanation():
    return """Here’s an extremely brief summary of the game *Coup*, highlighting the main actions, cards, and challenge-counter mechanics:

### Cards (Roles) with Actions and Blocks
1. **Duke**: Takes 3 coins from the treasury with TAX (not blockable), can block foreign aid action.
2. **Assassin**: Pays 3 coins to assassinate another player's character.
3. **Captain**: Steals 2 coins from another player, can block stealing.
4. **Ambassador**: Draws 2 cards to swap with court deck, can block stealing.
5. **Contessa**: Can block assassination.

### Additional Actions
- **Income**: Take 1 coin.
- **Foreign Aid**: Take 2 coins from the treasury (can be blocked by Duke).
- **Coup**: Pay 7 coins to launch a coup against another player, forcing them to lose an influence. This action cannot be blocked or challenged.

### Challenge
- If a player believes another player does not have the card they claim to be using, they can challenge them. A failed challenge results in the challenger losing an influence; a successful challenge results in the challenged player losing an influence.

### Counteractions
- Certain cards block specific actions (e.g., Duke blocks Foreign Aid, Captain and Ambassador block stealing, Contessa blocks assassination).

### Winning the Game
Be the last player with influence (cards) remaining to win the game."""


class Agent(BaseModel):
    game_state: Any
    coins: int

    current_stream: Optional[Any] = None
    stream_task: Optional[Any] = None

    name: str = Field(default_factory=str)
    personality: str = Field(default_factory=str)
    tasks: List[Any] = Field(default_factory=list)
    log: List[str] = Field(default_factory=list)
    cards: List[Any] = Field(default_factory=list)

    turn_without_tasks: int = 0
    is_active: bool = True

    async def interrupt(self):

        if self.current_stream:
            try:
                await self.current_stream.aclose()
            except Exception as e:
                pass
            await asyncio.sleep(1)
            self.current_stream = None

        if self.stream_task:
            self.stream_task.cancel()
            try:
                await self.stream_task
            except asyncio.CancelledError:
                pass
            self.stream_task = None
            self.current_stream = None

    async def parse_buffer(self, action: str, buffer: str, expected_actions: List[str]):
        if action == "ACTION":
            #print_text(f"{self.name} is taking ACTION: {buffer}", style="bold green")

            # Parse action into action and target player
            action_parts = buffer.split(" ")
            action_name = action_parts[0].strip()

            if not expected_actions:
                game_event_message = GameEventMessage(content="It is not your turn to take an action.")
                await self.receive_message(game_event_message)
                return

            if action_name not in expected_actions:
                # Invalid action name, send message to self with error
                game_event_message = GameEventMessage(content=f"Invalid action name: {action_name}. Must be one of {', '.join(expected_actions)}")
                await self.receive_message(game_event_message)
                return

            action = Action[action_name]

            if requires_target(action):
                target_player_name = action_parts[1].strip()

                # validate target player
                if target_player_name not in [player.name for player in self.game_state.players]:
                    game_event_message = GameEventMessage(content=f"Invalid target player: {target_player_name}. Must be one of {[player.name for player in self.game_state.players]}")
                    await self.receive_message(game_event_message)
                    return

                action_msg = ActionMessage(action=action, target=target_player_name, sender=self.name)
                await self.send_message(action_msg)
            elif action == Action.DISCARD:  # Requires a card
                card_name = action_parts[1]

                # validate card in hand
                if card_name not in [card.name for card in self.cards]:
                    game_event_message = GameEventMessage(content=f"Invalid card to discard: {card_name}. Must be one of {[card.name for card in self.cards]}")
                    await self.receive_message(game_event_message)
                    return

                card = Card[card_name]
                action_msg = ActionMessage(action=action, cards=[card], sender=self.name)
                await self.send_message(action_msg)


            elif action == Action.DISCARD_TWO:  # Requires two cards
                card1_name = action_parts[1].strip()
                card2_name = action_parts[2].strip()
                player_cards = [card.name for card in self.cards]

                if card1_name not in player_cards or card2_name not in player_cards:
                    game_event_message = GameEventMessage(content=f"Invalid cards to discard: {card1_name} {card2_name}. Must be two of {', '.join(player_cards)}")
                    await self.receive_message(game_event_message)

                card1 = Card[card1_name]
                card2 = Card[card2_name]

                action_msg = ActionMessage(action=action, cards=[card1, card2], sender=self.name)
                await self.send_message(action_msg)
            else:  # no target
                action_msg = ActionMessage(action=action, sender=self.name)
                await self.send_message(action_msg)
        elif action == "SPEECH":
            message = SpeechMessage(content=buffer, sender=self.name)
            await self.send_message(message)
        elif action == "THOUGHT":
            print_text(f"*{self.name} is THINKING: {buffer}*", style="italic grey")
            self.log.append(f"THOUGHT: {buffer}")

    async def process_stream(self, expected_actions: List[str]):
        # vars to collect the stream of chunks
        action = ""  # One of SPEECH, THOUGHT, ACTION
        buffer = ""
        try:
            async for chunk in self.current_stream:
                buffer += chunk
                ended = False
                next_action = ""

                if "SPEECH:" in buffer:
                    buffer = buffer.replace("SPEECH:", "")
                    next_action = "SPEECH"
                    ended = True
                elif "THOUGHT:" in buffer:
                    buffer = buffer.replace("THOUGHT:", "")
                    next_action = "THOUGHT"
                    ended = True
                elif "ACTION:" in buffer:
                    buffer = buffer.replace("ACTION:", "")
                    next_action = "ACTION"
                    ended = True

                if ended:
                    # Remove END
                    buffer = buffer.replace("END", "").strip()

                    if action and buffer:
                        #print_text(f"{self.name} PARSING {action} {buffer} \n Tasks: {self.tasks}\n-----")
                        await self.parse_buffer(action, buffer, expected_actions)
                        buffer = ""
                    action = next_action

            if action and buffer:
                buffer = buffer.replace("END", "").strip()
                #print_text(f"{self.name} PARSING {action} {buffer} \n Tasks: {self.tasks}\n-----")
                await self.parse_buffer(action, buffer, expected_actions)
        except asyncio.CancelledError:
            pass

    async def receive_message(self, message: Message):
        """
        Agent can receive speech message or task message denoting that they must do something
        """
        #print_text(f"{self.name} RECEIVED {message.message_type}: {message.content}", style="bold blue")

        await self.interrupt()

        if message.message_type == MessageType.TASK_COMPLETE:
            if message in self.tasks:
                self.tasks.remove(message)
            return  # Don't respond to task completion messages
        if message.message_type == MessageType.TASK:
            self.turn_without_tasks = 0
            self.tasks.append(message)
        elif message.message_type == MessageType.SPEECH:
            self.log.append(message.sender + ": " + message.content)

            if message.sender == self.name:
                # Don't respond to your own messages
                return
        elif message.message_type == MessageType.GAME_EVENT:
            self.log.append("GAME: " + message.content)
            #self.game_log.append(message.content)

        if self.turn_without_tasks > 4:  # force the player with the task to play an action
            return

        log_str = "\n".join(self.log[-20:])
        player_info_str = "\n".join([f"{player.name} has {player.coins} coins with {len(player.cards)} cards." for player in self.game_state.players])

        expected_actions = []

        if self.tasks:
            tasks_str = ""

            for task in self.tasks:
                if task.expected_actions:
                    expected_actions.extend(list(map(lambda x: str(x.name), task.expected_actions)))
                tasks_str += task.content + " You must NOW output one of the following actions. ACTION: " + ", ".join(map(map_action_to_output_format, task.expected_actions)) + "\n"

            # print logs and tasks:
            #print_text(f"{self.name} STARTING STREAM WITH TASKS: {log_str} | {tasks_str} \n------------------")

            system_msg = f"""Your name is {self.name}. You are a strategic player in the game of Coup. 
{game_explanation()}

Your personality is:
{self.personality}

In your communications, you can choose to use SPEECH, THOUGHT, or ACTION.
- Use 'SPEECH:' to communicate anything to other players.
- Use 'THOUGHT:' to reflect on your best course of action that maximizes your chances of winning, what cards you think others have, how you should respond to other players, etc.
- Use 'ACTION:' to make a strategic move, specifying the action and the target player.
We recommend that you think through your strategy with multiple thoughts (THOUGHT) before committing to any action.

Here is the log of conversations, thoughts and game events:
{log_str}

Your output should strictly follow this format, with each new line beginning with one of SPEECH, THOUGHT, or ACTION:
SPEECH: <what you want to say to others to manipulate/collaborate with them>
THOUGHT: <thoughts that lead to maximizing your chances of winning by ANY means>
ACTION: <action name> <target player>

You can output multiple in sequence.
Example 1:
THOUGHT: Since Susan has the most coins, I should target her.
SPEECH: What cards do you guys think Susan has?

Example 2:
THOUGHT: Ok it looks like Susan doesn't have the Contessa to counter my Assassin
ACTION: ASSASSINATE Susan

Example 3:
THOUGHT: I think my duke card is probably more valuable than my captain card
ACTION: DISCARD CAPTAIN

Example 4:
THOUGHT: It's too risky to challenge Susan's Steal because it's likely she has the Captain
ACTION: NO_CHALLENGE
     
The following players are in the game:
{player_info_str}

Here are your cards:
{', '.join([str(card) for card in self.cards])}

Here are your tasks:
{tasks_str}

It is currently turn {self.game_state.current_turn}.

- Use SPEECH if you want to influence other players. But don't use it excessively.
- Only use THOUGHT if you have an insightful thought that is not already in your inner thoughts.
- Use ACTION if you are ready to commit to a strategic move or if the conversation is getting too repetitive.

{"You must NOW output an action from your task." if self.turn_without_tasks > 3 else ""}

Start your output:"""

            #print(f"{self.name} STARTING STREAM WITH TASKS:", tasks_str)

        else:
            #print_text(f"{self.name} STARTING STREAM: {log_str}")

            system_msg = f"""Your name is {self.name}. You are a strategic player in the game of Coup. 
{game_explanation()}     

Your personality is:
{self.personality}
        
In your communications, you can choose to use SPEECH or THOUGHT.
- Use 'SPEECH:' to communicate anything to other players.
- Use 'THOUGHT:' to reflect on your strategy, what cards you think others have, how you should respond to other players, etc.

It is not your turn at the moment but you can use SPEECH and THOUGHT. You can:
 - think about your strategy in terms of how you will interact with the other players
 - try to figure out what cards the other players have
 - react to other players' actions/words

Here is the log of conversations, your thoughts and game events:
{log_str}

Your output should strictly follow this format, with each new line beginning with one of SPEECH, THOUGHT, or ACTION:
SPEECH: <what you want to say to others>
THOUGHT: <your internal considerations>

You can output multiple in sequence.
Example 1:
THOUGHT: Since Susan has the most coins, I should target her.
SPEECH: What cards do you guys think Susan has?

Example 2:
THOUGHT: Ok it looks like Susan doesn't have the Contessa to counter my Assassin. I should tell everyone that, so we can bring her down to 1 card like the rest of us.
SPEECH: I don't think Susan has the Contessa

The following players are in the game:
{player_info_str}

It is currently turn {self.game_state.current_turn}.

- Use SPEECH if you want to influence other players. But don't use it excessively.
- Only use THOUGHT if you have an insightful thought that is not already in your inner thoughts.
- You can simply write END if you have nothing to do or say or if there is too much conversation happening.

Start your output:"""
            #print(f"{self.name} STARTING STREAM:")

        """self.current_stream = client.chat.completions.create(
            model='gpt-4o-mini',
            messages=[{'role': 'system', 'content': system_msg}],
            temperature=0.3,  # little bit of creativity, but should be following the format & given knowledge
            stream=True
        )"""

        self.turn_without_tasks += 1
        self.current_stream = get_openai_stream(system_msg)
        self.stream_task = await asyncio.create_task(self.process_stream(expected_actions))

    async def send_message(self, message: Message):
        #print(f"{self.name} SENDING", message)
        await self.game_state.handle_message(message)

    def __repr__(self):
        return self.name
