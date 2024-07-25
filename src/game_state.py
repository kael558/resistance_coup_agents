import asyncio
import random
from typing import List, Optional

from pydantic import BaseModel
from rich.table import Table, Column
from rich.text import Text

from src.datatypes import get_base_actions, get_challenge_actions, get_counter_actions, Message, Action, Card, GameEventMessage, SpeechMessage, ActionMessage, TaskMessage, MessageType, CARD_FOREGROUND_COLOR_MAP, CARD_BACKGROUND_COLOR_MAP
from src.agent import Agent
from src.helper import can_be_challenged, requires_target, has_card_for_action, can_be_countered, has_challenge_card, get_counter_card, name_list, personality_list
from src.print_utils import print_text, clear_screen, print_table


class TurnData(BaseModel):
    source_player: Agent
    action: Action
    target_player: Optional[Agent]

    countering_player: Optional[Agent] = None


class GameState:
    def __init__(self, num_players):
        self.num_players = num_players
        self.players: List[Agent] = []

        self.current_turn = 0
        self.current_turn_data = None

        self.player_turn_index = 0

        self.expected_actions = []

        self.treasury = 50
        self.deck = [Card.DUKE] * 3 + [Card.ASSASSIN] * 3 + [Card.CAPTAIN] * 3 + [Card.AMBASSADOR] * 3 + [Card.CONTESSA] * 3

    async def setup_game(self):
        clear_screen()
        random.shuffle(self.deck)
        names = random.sample(name_list, self.num_players)
        personalities = random.sample(personality_list, self.num_players)

        for i in range(self.num_players):
            player = Agent(name=names[i],
                           personality=personalities[i],
                           game_state=self,
                           coins=1 if self.num_players == 2 else 2)
            player.cards = [self.deck.pop(), self.deck.pop()]
            self.players.append(player)

        print_table(generate_player_info_table(self.players))
        # Give task to first player
        await self.send_task_message(self.players[0], "You are the first player starting the game. Choose an action to perform.", get_base_actions())
        self.treasury -= (self.num_players * 2)

    def get_all_active_players(self) -> List[Agent]:
        return [p for p in self.players if p.is_active]

    def get_all_other_players(self, player: Agent) -> List[Agent]:
        return [p for p in self.players if p != player and p.is_active]

    def get_all_players_who_can_counter(self, player: Agent) -> List[Agent]:
        if self.current_turn_data.action == Action.ASSASSINATE or self.current_turn_data.action == Action.STEAL:
            # Only the target player can counter
            return [self.current_turn_data.target_player]
        elif self.current_turn_data.action == Action.FOREIGN_AID:
            # All players can counter
            return self.get_all_other_players(player)

        return []

    async def send_task_message(self, players: List[Agent] or Agent, content: str, expected_actions: List[Action] = None):
        if isinstance(players, Agent):
            players = [players]

        # Adds a bit of randomness to the generation
        random.shuffle(players)

        print_text(f"Sending task message to {players}: {content.upper()}", style="bold cyan", rainbow=False, with_markup=True)

        for player in players:
            task_msg = TaskMessage(content=content, expected_actions=expected_actions)

            # Add task to expected actions for player
            self.expected_actions.append((player, task_msg))

        # Important to run this after all expected actions have been added
        for player, task_msg in self.expected_actions:
            # run this async
            await player.receive_message(task_msg)

    async def reset_expected_actions(self):
        for (expected_player, task_msg) in self.expected_actions:
            # send task completion task to player
            task_msg.message_type = MessageType.TASK_COMPLETE
            await expected_player.receive_message(task_msg)

        self.expected_actions = []

    def swap_card(self, player: Agent, card: Card):
        # Remove card from current players hand
        player.cards.remove(card)

        # Add card to deck
        self.deck.append(card)

        # Shuffle deck
        random.shuffle(self.deck)

        # Add new card to player's hand
        player.cards.append(self.deck.pop())

    def _take_coin_from_treasury(self, player: Agent, number_of_coins: int):
        coins = min(number_of_coins, self.treasury)
        self.treasury -= coins
        player.coins += coins

    def _give_coin_to_treasury(self, player: Agent, number_of_coins: int):
        self.treasury += number_of_coins
        player.coins -= number_of_coins

    async def do_action(self, countered: bool = False):
        # get action from current turn
        action = self.current_turn_data.action
        match action:
            case Action.INCOME:
                self._take_coin_from_treasury(self.current_turn_data.source_player, 1)
            case Action.FOREIGN_AID:
                if countered:
                    return
                self._take_coin_from_treasury(self.current_turn_data.source_player, 2)
            case Action.TAX:
                self._take_coin_from_treasury(self.current_turn_data.source_player, 3)
            case Action.ASSASSINATE:
                self._give_coin_to_treasury(self.current_turn_data.source_player, 3)
                if countered:
                    return

                content = f"You have been assassinated by {self.current_turn_data.source_player.name}. Choose a card to discard."
                await self.send_task_message(self.current_turn_data.target_player, content, [Action.DISCARD])
            case Action.EXCHANGE:
                content = f"You are exchanging cards. You received 2 new cards, now you must choose 2 cards to discard."
                await self.send_task_message(self.current_turn_data.source_player, content, [Action.DISCARD_TWO])
            case Action.STEAL:
                if not countered:
                    coins = min(2, self.current_turn_data.target_player.coins)
                    self.current_turn_data.source_player.coins += coins
                    self.current_turn_data.target_player.coins -= coins
            case Action.COUP:
                self._give_coin_to_treasury(self.current_turn_data.source_player, 7)
                content = f"You have been couped by {self.current_turn_data.source_player.name}. Choose a card to discard."
                await self.send_task_message(self.current_turn_data.target_player, content, [Action.DISCARD])

    async def handle_message(self, message: Message):
        if isinstance(message, ActionMessage):
            print_text(f"{message.sender} sent ACTION: {str(message)}", style="bold green", with_markup=True)
            await self.handle_action(message)
        elif isinstance(message, SpeechMessage):
            print_text(f"{message.sender}: {message.content}")
            # Send the message to all agents
            for player in self.get_all_active_players():
                await player.receive_message(message)

    async def handle_action(self, message: ActionMessage):
        action = message.action
        player_name = message.sender
        player = next(p for p in self.players if p.name == player_name and p.is_active)

        target_name = message.target
        target = next((p for p in self.players if p.name == target_name and p.is_active), None)

        # Check if action receiving is in the expected_actions list
        expected_actions_str = ", ".join([f"{player.name}: {task_msg.expected_actions}" for player, task_msg in self.expected_actions])

        for (expected_player, task_msg) in self.expected_actions:
            if player == expected_player and action in task_msg.expected_actions:
                # Validate the action here
                if requires_target(action):
                    if not target:
                        players = self.get_all_other_players(player)
                        game_event_msg = GameEventMessage(content=f"Action {action} requires a target. One of {players} must be targeted.")
                        await player.receive_message(game_event_msg)
                        return

                    if action == Action.STEAL and target.coins == 0:
                        game_event_msg = GameEventMessage(content=f"Player {target.name} has no coins to steal. Please choose another target or another action.")
                        await player.receive_message(game_event_msg)
                        return

                #print_text(f"Player {player.name} sent expected action: {action}. Remaining actions: {len(self.expected_actions)}", style="bold green", with_markup=True)
                self.expected_actions.remove((expected_player, task_msg))

                # send task completion task to player
                task_msg.message_type = MessageType.TASK_COMPLETE
                await player.receive_message(task_msg)
                break
        else:  # Action is not expected,
            # Check if player is supposed to send other actions
            for (expected_player, task_msg) in self.expected_actions:
                if player == expected_player:
                    expected_actions_str = ", ".join([str(expected_action) for expected_action in task_msg.expected_actions])
                    game_event_msg = GameEventMessage(content=f"You sent an unexpected action: {action}. Please send one of the expected actions: {expected_actions_str}")
                    await player.receive_message(game_event_msg)
                    return

            # Otherwise, it's not their turn
            game_event_msg = GameEventMessage(content=f"You sent an unexpected action: {action}. Please wait for your turn.")
            await player.receive_message(game_event_msg)
            return

        # Action is valid so we move to the next stage
        if action in get_base_actions():
            self.current_turn_data = TurnData(source_player=player, action=action, target_player=target)
            tasks = []
            if can_be_challenged(action):
                # Ask all players if they would like to challenge
                players = self.get_all_other_players(player)
                task = self.send_task_message(players, f"Player {player.name} is attempting to perform action {action.name}{' on ' + target.name if target else ''}. Would you like to challenge that they don't have the required cards to perform that action?", get_challenge_actions())
                tasks.append(task)

            if can_be_countered(action):
                # Ask all players if they would like to counter
                players = self.get_all_other_players(player)
                task = self.send_task_message(players, f"Player {player.name} is attempting to perform action {action.name}{' on ' + target.name if target else ''}. Would you like to counter their action?", get_counter_actions())
                tasks.append(task)

            if not tasks:
                # No challenge or counter required
                await self.do_action()
            else:
                # Wait for all tasks to complete
                await asyncio.gather(*tasks)

        elif action in get_challenge_actions():
            if action == Action.CHALLENGE:
                # Issue a challenge and also remove all expected actions

                # Iterate the expected actions and remove all challenges
                await self.reset_expected_actions()

                # TODO refactor & simplify this logic
                if self.current_turn_data.countering_player:  # Challenge issued to countering player's action
                    if card := has_challenge_card(self.current_turn_data.action, self.current_turn_data.countering_player.cards):
                        # Challenge fails because countering player has the card

                        self.swap_card(self.current_turn_data.countering_player, card)
                        await self.do_action(countered=True)

                        task_msg = f"You challenged {self.current_turn_data.countering_player.name} on their counter to action {self.current_turn_data.action}. Unfortunately, they had the required card and you lost the challenge so you must discard a card."
                        await self.send_task_message(player, task_msg, [Action.DISCARD])
                    else:
                        # Challenge succeeds
                        await self.do_action()

                        task_msg = f"You were caught in a bluff. You do not have the card to counter the action {self.current_turn_data.action}. You must discard a card."
                        await self.send_task_message(self.current_turn_data.countering_player, task_msg, [Action.DISCARD])
                else:  # Challenge issued to action
                    if card := has_card_for_action(self.current_turn_data.action, self.current_turn_data.source_player.cards):
                        self.swap_card(self.current_turn_data.source_player, card)
                        await self.do_action()

                        # Challenge fails because challenged player has the card
                        task_msg = f"You challenged {self.current_turn_data.source_player.name} on their action {self.current_turn_data.action}. Unfortunately, they had the required card and you lost the challenge so you must discard a card."
                        await self.send_task_message(player, task_msg, [Action.DISCARD])
                    else:
                        # Challenge succeeds, however it depends if it was a challenge to the counter or the action
                        await self.do_action(countered=True)

                        # Challenge succeeds
                        task_msg = f"You were caught in a bluff. You do not have the card for action {self.current_turn_data.action}. You must discard a card."
                        await self.send_task_message(self.current_turn_data.source_player, task_msg, [Action.DISCARD])
            elif action == Action.NO_CHALLENGE:
                # if everyone has responded with no challenge, then move to next stage
                if len(self.expected_actions) == 0:
                    if self.current_turn_data.countering_player:
                        await self.do_action(countered=True)
                    elif players := self.get_all_players_who_can_counter(player):
                        await self.send_task_message(players, f"Player {player.name} is attempting to perform action {self.current_turn_data.action}. Would you like to counter their action?", get_counter_actions())
                    else:
                        await self.do_action()

        elif action in get_counter_actions():
            # Someone has issued a counter
            if action == Action.COUNTER:
                # Set the data in the turn data and then ask if anyone would like challenge
                await self.reset_expected_actions()
                self.current_turn_data.countering_player = player

                players = self.get_all_other_players(player)
                await self.send_task_message(players, f"Player {player.name} is claiming they have {get_counter_card(self.current_turn_data.action)} and is attempting to counter action {self.current_turn_data.action}. Would you like to challenge the counter?", get_challenge_actions())
            elif action == Action.NO_COUNTER:
                # if everyone has responded with no counter, then do the action
                if len(self.expected_actions) == 0:
                    await self.do_action()

        elif action == Action.DISCARD:
            # Discard a card
            player.cards.remove(message.cards[0])
            self.deck.append(message.cards[0])
            random.shuffle(self.deck)
        elif action == Action.DISCARD_TWO:
            # Discard 2 cards (as they received 2 cards from the exchange)
            for card in message.cards:
                player.cards.remove(card)
                self.deck.append(card)

            random.shuffle(self.deck)

        # if no more actions required for this turn, then move to next turn
        if len(self.expected_actions) == 0:
            # Check if a player has been eliminated
            for player in self.get_all_active_players():
                if len(player.cards) == 0:
                    player.is_active = False

                    active_players = self.get_all_active_players()
                    # Player has been eliminated
                    print_text(f"Player {player.name} has been eliminated from the game!", style="bold red", with_markup=True)
                    #game_event_msg = GameEventMessage(content=f"Player {player.name} has been eliminated from the game.")

                    # Check if a winner has been found
                    if len(active_players) == 1:
                        print_text(f"Player {active_players[0].name} has won the game!", style="bold", rainbow=True, with_markup=True)
                        return

            self.current_turn += 1
            self.current_turn_data = None

            self.player_turn_index += 1
            next_player = self.players[self.player_turn_index % len(self.players)]
            while not next_player.is_active:
                self.player_turn_index += 1
                next_player = self.players[self.player_turn_index % len(self.players)]

            table = generate_player_summary_table(self.players, self.player_turn_index, self.current_turn)
            print_table(table)

            await self.send_task_message(next_player, f"Player {next_player.name} it is your turn. Choose an action to perform.", get_base_actions())


def generate_player_info_table(players: List[Agent]):
    """Generate a table to show their name, personality and starting cards"""
    table = Table("Player", "Personality", Column(header="Cards", justify="center", min_width=40))
    for player in players:
        name_text = Text.from_markup(f":robot: {player.name}")
        personality_text = Text.from_markup(f":person_tipping_hand: {player.personality}")

        card_text = Text()
        for card in player.cards:
            card_text.append(
                str(card), style=f"{CARD_FOREGROUND_COLOR_MAP[card]} on {CARD_BACKGROUND_COLOR_MAP[card]}"
            )
            card_text.append(" ")

        table.add_row(name_text, personality_text, card_text)

    return table


def generate_player_summary_table(players: List[Agent], current_player_index: int, current_turn: int) -> Table:
    """Generate a table of the players"""
    print_text(f"End of Turn {current_turn}", style="bold", with_markup=True)
    table = Table("Player", "Coins", Column(header="Cards", justify="center", min_width=40))
    for ind, player in enumerate(players):
        player_text = Text.from_markup(f":robot: {str(player.name)}")

        if ind == current_player_index:
            player_text.stylize("bold magenta")

        coin_text = Text(str(player.coins), style="gray")

        card_text = Text()
        if player.is_active:
            for card in player.cards:
                card_text.append(
                    str(card), style=f"{CARD_FOREGROUND_COLOR_MAP[card]} on {CARD_BACKGROUND_COLOR_MAP[card]}"
                )
                card_text.append(" ")
        else:
            card_text = Text.from_markup(":skull:")

        table.add_row(player_text, coin_text, card_text)

    return table
