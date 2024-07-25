import json
import os
from typing import List, Optional

import aiohttp
from dotenv import load_dotenv

from src.datatypes import Action, Card

load_dotenv()


async def get_openai_stream(system_message: str):
    url = 'https://api.openai.com/v1/chat/completions'
    headers = {
        'Authorization': f'Bearer {os.environ.get("OPENAI_API_KEY")}',
        'Content-Type': 'application/json',
    }
    data = {
        'model': 'gpt-4o-mini',
        'messages': [{'role': 'system', 'content': system_message}],
        'temperature': 0.3,  # Should be based on game knowledge but also with a bit of creativity
        'stream': True,
    }

    async with aiohttp.ClientSession() as session:
        async with session.post(url, headers=headers, json=data) as response:
            if response.status != 200:
                raise Exception(f"Request failed with status {response.status}")

            async for line in response.content:
                chunk = line.decode('utf-8')

                # remove data: and json loads
                chunk = chunk[5:]
                chunk = chunk.strip()

                try:
                    if chunk:
                        json_data = json.loads(chunk)
                        yield json_data['choices'][0]['delta']['content']
                except:
                    pass


def has_card_for_action(action: Action, cards: List[Card]) -> Optional[Card]:
    if action == Action.TAX and Card.DUKE in cards:
        return Card.DUKE
    elif action == Action.ASSASSINATE and Card.ASSASSIN in cards:
        return Card.ASSASSIN
    elif action == Action.STEAL and Card.CAPTAIN in cards:
        return Card.CAPTAIN
    elif action == Action.EXCHANGE and Card.AMBASSADOR in cards:
        return Card.AMBASSADOR

    return None


def has_challenge_card(action: Action, cards: List[Card]) -> Optional[Card]:
    if action == Action.ASSASSINATE and Card.CONTESSA in cards:
        return Card.CONTESSA
    elif action == Action.STEAL and Card.CAPTAIN in cards:
        return Card.CAPTAIN
    elif action == Action.FOREIGN_AID and Card.DUKE in cards:
        return Card.DUKE

    return None


def get_counter_card(action: Action) -> Optional[Card]:
    if action == Action.ASSASSINATE:
        return Card.CONTESSA
    elif action == Action.STEAL:
        return Card.CAPTAIN
    elif action == Action.FOREIGN_AID:
        return Card.DUKE

    return None


def can_be_countered(action: Action):
    return action in [Action.ASSASSINATE, Action.STEAL, Action.FOREIGN_AID]


def can_be_challenged(action: Action):
    return action in [Action.ASSASSINATE, Action.STEAL, Action.TAX, Action.EXCHANGE]


def requires_target(action: Action):
    return action in [Action.ASSASSINATE, Action.STEAL, Action.COUP]




name_list = ["Alice", "Bob", "Charlie", "David", "Eve", "Frank", "Grace", "Heidi", "Ivan", "Judy", "Kevin", "Lily", "Mia", "Nina", "Oliver", "Penny", "Quinn", "Riley", "Sara", "Tom", "Ursula", "Violet", "Wendy", "Xander", "Yara", "Zara"]

personality_list = [
    "The Strategist: Calm and collected, they meticulously plan each move. They observe every player's actions and make calculated decisions. Rarely speaks, but when they do, it's with purpose.",
    "The Bluffmaster: Bold and charismatic, they thrive on deception. They lie confidently and often, keeping everyone guessing about their true intentions. Enjoys making big, dramatic moves.",
    "The Analyzer: Analytical and precise, they keep track of every card played and every statement made. Often seen scribbling notes and formulating theories. Prefers to let others make mistakes and then strike.",
    "The Aggressor: Loud and confrontational, they enjoy taking risks and making bold moves. They often call out bluffs and make others uncomfortable with their aggressive play style. Enjoys the thrill of direct confrontations.",
    "The Diplomat: Smooth-talking and persuasive, they excel at forming temporary alliances and negotiating deals. They avoid direct conflict and instead manipulate others into doing their bidding.",
    "The Silent Observer: Quiet and reserved, they rarely speak but observe everything. They make unpredictable moves, keeping others on edge. Their silence makes them a wild card.",
    "The Gambler: Thrives on taking risks and making high-stakes plays. They are unpredictable and enjoy the thrill of uncertainty. Their gameplay is erratic but occasionally brilliant.",
    "The Schemer: Always plotting, they work behind the scenes to influence the game subtly. They enjoy setting traps and watching others fall into them. Their moves are often well-hidden until it's too late.",
    "The Emotional Player: Highly reactive and driven by emotions. Their mood swings can drastically affect their gameplay, making them unpredictable. They can be a fierce opponent or a sudden ally, depending on their emotional state.",
    "The Veteran: Experienced and wise, they have played many games and seen many strategies. They offer sage advice (sometimes misleading) and have a knack for predicting others' moves. Their calm demeanor hides a sharp mind."
]
