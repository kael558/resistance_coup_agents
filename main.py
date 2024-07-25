import asyncio
import sys

from src.game_state import GameState
from src.print_utils import print_prompt, print_text


async def main():
    while True:
        num_players = print_prompt("Enter the number of players (2-6)")
        if num_players.isdigit() and 2 <= int(num_players) <= 6:
            break
        print_prompt("Invalid input. Please enter a number between 2 and 6.")

    game = GameState(int(num_players))
    await game.setup_game()


if __name__ == "__main__":
    try:
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        asyncio.run(main())
    except KeyboardInterrupt:
        print_text("GAME OVER", rainbow=True)
        sys.exit(130)




