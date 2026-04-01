"""
fall_in.multiplayer — Multiplayer adapter and state model layer.

This package contains:
  - models.py   : Network-safe state DTOs (PublicMatchState, PrivatePlayerState,
                  SeatIdentity, MatchCardPublic, AccountProgressRef).
  - local_adapter.py (PR-04+) : Wraps existing single-player GameRules as an
                  adapter so GameScene can remain the same renderer.
  - remote_adapter.py (PR-04+): Receives server snapshots and feeds them to
                  GameScene via the same adapter interface.

PR-01 adds models.py only.  No live adapters yet.
"""
