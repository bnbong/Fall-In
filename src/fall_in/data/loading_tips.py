"""
Loading screen gameplay tips.
Displayed randomly during scene transitions.
"""

import random

LOADING_TIPS = [
    "위험도가 높은 카드일수록 보라색 원으로 표시됩니다.",
    "UI바 좌측 격납고 아이콘에 해당 라운드에 누적된 벌칙 카드의 개수가 표시됩니다.",
    "누적 위험도가 66점을 넘으면 탈락합니다!",
    "줄의 6번째 자리에 카드를 놓으면 해당 줄의 모든 카드를 가져갑니다.",
    "친해진 병사를 빼돌리면 훈련에 실패하더라도 좋은 추억을 만들 수 있습니다.",
    "빼돌린 병사들 군번 조합에 따라 게임 오버 화면이 달라집니다.",
    "면담을 통해 병사들을 알아가고 친해질 수 있습니다.",
    "승리하면 더 많은 수당을 받을 수 있습니다.",
    "각 라운드마다 10장의 카드가 배급됩니다.",
    "병사들은 오름차순 군번으로 배치됩니다. 순서를 잘 생각하세요!",
    "위험도 1짜리 카드도 많이 모이면 위험합니다.",
    "헤쳐 모여! 게임의 규칙은 보드게임 젝스님트와 동일합니다.",
]


def get_random_tip() -> str:
    """Return a random gameplay tip."""
    return random.choice(LOADING_TIPS)
