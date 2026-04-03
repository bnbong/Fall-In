"""
Room business logic.

All methods are synchronous (no I/O) so they can be called from both sync
and async contexts. The WS handler awaits only the network sends, not these.

Invariants enforced here:
  - Only the host (seat 0 initially, or re-assigned on leave) can start.
  - Starting fills every empty seat with a bot before phase transitions.
  - Leaving as the last human destroys the room.
  - Host role transfers to the lowest remaining seat on host departure.
"""

from typing import Optional

from app.models.room import Room, RoomParticipant, RoomPhase, SeatControllerType
from app.repositories.room_repo import InMemoryRoomRepo


class RoomError(Exception):
    pass


class RoomService:
    def __init__(self, repo: InMemoryRoomRepo) -> None:
        self.repo = repo

    # ------------------------------------------------------------------
    # Create
    # ------------------------------------------------------------------

    def create_room(
        self,
        display_name: str,
        connection_id: str,
        user_id: Optional[str] = None,
    ) -> Room:
        room_code = self.repo.generate_room_code()
        host = RoomParticipant(
            seat_index=0,
            display_name=display_name,
            controller_type=SeatControllerType.REMOTE,
            is_ready=False,
            user_id=user_id,
            connection_id=connection_id,
        )
        room = Room(
            room_code=room_code,
            host_seat_index=0,
            phase=RoomPhase.WAITING,
            participants={0: host},
        )
        self.repo.create(room)
        return room

    # ------------------------------------------------------------------
    # Join
    # ------------------------------------------------------------------

    def join_room(
        self,
        room_code: str,
        display_name: str,
        connection_id: str,
        user_id: Optional[str] = None,
    ) -> Room:
        room = self.repo.get(room_code)
        if room is None:
            raise RoomError("Room not found")
        if room.phase != RoomPhase.WAITING:
            raise RoomError("Room is not accepting new players")
        seat = room.next_available_seat()
        if seat is None:
            raise RoomError("Room is full")
        room.participants[seat] = RoomParticipant(
            seat_index=seat,
            display_name=display_name,
            controller_type=SeatControllerType.REMOTE,
            is_ready=False,
            user_id=user_id,
            connection_id=connection_id,
        )
        self.repo.update(room)
        return room

    # ------------------------------------------------------------------
    # Leave
    # ------------------------------------------------------------------

    def leave_room(self, room_code: str, seat_index: int) -> Optional[Room]:
        """
        Remove the participant at seat_index.

        Returns the updated Room, or None if the room was destroyed.

        Destroy conditions:
          - All participants are gone (WAITING phase normal case).
          - No human (REMOTE) participants remain — bots-only state is
            unrecoverable, so the room is cleaned up immediately.  This
            prevents orphaned STARTING rooms after the last human leaves
            or disconnects.

        Host is re-assigned to the lowest-indexed remaining REMOTE seat.
        """
        room = self.repo.get(room_code)
        if room is None:
            return None

        room.participants.pop(seat_index, None)

        remaining_humans = [
            p for p in room.participants.values()
            if p.controller_type == SeatControllerType.REMOTE
        ]
        if not remaining_humans:
            self.repo.delete(room_code)
            return None

        if room.host_seat_index == seat_index:
            room.host_seat_index = min(p.seat_index for p in remaining_humans)

        self.repo.update(room)
        return room

    # ------------------------------------------------------------------
    # Ready toggle
    # ------------------------------------------------------------------
    #
    # READY_SET is cosmetic / informational only.
    # The host can call start_room() regardless of whether other players
    # have toggled ready.  This is an intentional design decision:
    # the host controls pacing; ready flags are a social signal, not a gate.
    # This rule is fixed here before PR-04 match handoff is built.

    def set_ready(self, room_code: str, seat_index: int, is_ready: bool) -> Room:
        room = self.repo.get(room_code)
        if room is None:
            raise RoomError("Room not found")
        participant = room.participants.get(seat_index)
        if participant is None:
            raise RoomError("Seat not found in room")
        participant.is_ready = is_ready
        self.repo.update(room)
        return room

    # ------------------------------------------------------------------
    # Start
    # ------------------------------------------------------------------

    def start_room(self, room_code: str, requesting_seat: int) -> Room:
        """
        Host starts the lobby.  Empty seats (1-3) are filled with AI bots.
        Phase transitions to STARTING so the match engine (PR-04) can pick up.
        """
        room = self.repo.get(room_code)
        if room is None:
            raise RoomError("Room not found")
        if room.host_seat_index != requesting_seat:
            raise RoomError("Only the host can start the room")
        if room.phase != RoomPhase.WAITING:
            raise RoomError("Room is already starting")

        for seat_idx in range(4):
            if seat_idx not in room.participants:
                room.participants[seat_idx] = RoomParticipant(
                    seat_index=seat_idx,
                    display_name=f"AI Bot {seat_idx + 1}",
                    controller_type=SeatControllerType.BOT,
                    is_ready=True,
                    user_id=None,
                    connection_id=None,
                )

        room.phase = RoomPhase.STARTING
        self.repo.update(room)
        return room

    # ------------------------------------------------------------------
    # Lookup
    # ------------------------------------------------------------------

    def find_participant_room(self, connection_id: str) -> Optional[tuple[str, int]]:
        """Return (room_code, seat_index) or None if not in any room."""
        return self.repo.find_by_connection(connection_id)
