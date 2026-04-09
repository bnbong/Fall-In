"""
Network message type definitions for Fall-In multiplayer protocol.

Defines the string constants for every message type exchanged between client
and server over WebSocket.  No transport code lives here — these are pure
identifiers used by serializers and the future ws_client / server handlers.

Naming convention:
  Client → Server  :  verb in imperative form  (CARD_SELECT, EMOTE_SEND …)
  Server → Client  :  noun / past-tense form   (MATCH_START, TURN_RESOLVED …)
"""

from enum import Enum


class ClientMessageType(str, Enum):
    """Messages the client sends to the server."""

    # Handshake
    WS_HELLO = "WS_HELLO"

    # Authentication
    AUTH_LOGIN = "AUTH_LOGIN"
    AUTH_GUEST = "AUTH_GUEST"

    # Room management
    ROOM_CREATE = "ROOM_CREATE"
    ROOM_JOIN = "ROOM_JOIN"
    ROOM_LEAVE = "ROOM_LEAVE"
    READY_SET = "READY_SET"
    ROOM_START = "ROOM_START"

    # Quick match queue (server uses QUICK_MATCH_* prefix)
    QUICK_MATCH_JOIN = "QUICK_MATCH_JOIN"
    QUICK_MATCH_LEAVE = "QUICK_MATCH_LEAVE"

    # In-game actions
    CARD_SELECT = "CARD_SELECT"
    ROUND_READY = "ROUND_READY"
    EMOTE_SEND = "EMOTE_SEND"
    EMOTE_MUTE = "EMOTE_MUTE"

    # Connection management
    PING = "PING"
    RECONNECT = "RECONNECT"


class ServerMessageType(str, Enum):
    """Messages the server sends to the client."""

    # Handshake
    WS_WELCOME = "WS_WELCOME"

    # Authentication
    AUTH_OK = "AUTH_OK"

    # Room management
    ROOM_STATE = "ROOM_STATE"

    # Match lifecycle
    MATCH_FOUND = "MATCH_FOUND"
    MATCH_START = "MATCH_START"
    MATCH_RESULT = "MATCH_RESULT"

    # Quick match queue
    QUEUE_JOINED = "QUEUE_JOINED"
    QUEUE_LEFT = "QUEUE_LEFT"

    # In-game phases
    PHASE_SELECTING = "PHASE_SELECTING"
    TURN_REVEAL_START = "TURN_REVEAL_START"
    TURN_REVEAL_STEP = "TURN_REVEAL_STEP"
    TURN_RESOLVED = "TURN_RESOLVED"
    ROUND_RESULT = "ROUND_RESULT"

    # Per-client state pushes (sent only to the recipient)
    PRIVATE_HAND_STATE = "PRIVATE_HAND_STATE"

    # Shared state broadcast
    PUBLIC_BOARD_STATE = "PUBLIC_BOARD_STATE"

    # Presence / connection
    PLAYER_PRESENCE = "PLAYER_PRESENCE"
    PLAYER_DISCONNECTED = "PLAYER_DISCONNECTED"
    PLAYER_RECONNECTED = "PLAYER_RECONNECTED"
    SEAT_BOT_TAKEOVER = "SEAT_BOT_TAKEOVER"
    RECONNECT_TOKEN = "RECONNECT_TOKEN"
    RECONNECT_OK = "RECONNECT_OK"

    # Social
    EMOTE_BROADCAST = "EMOTE_BROADCAST"
    EMOTE_MUTE_ACK = "EMOTE_MUTE_ACK"

    # Errors
    ERROR = "ERROR"

    # Connection management
    PONG = "PONG"
