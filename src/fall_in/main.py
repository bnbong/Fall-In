"""
Main entry point for 헤쳐 모여! (Fall In!)
"""

from fall_in.core.game_manager import GameManager


def main() -> None:
    """Main function - game entry point"""
    game = GameManager()
    game.initialize()
    game.run()


if __name__ == "__main__":
    main()
