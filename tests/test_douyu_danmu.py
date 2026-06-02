from datetime import datetime
import socket
import unittest

from src.douyu_danmu import (
    decode_fields,
    encode_fields,
    pack_message,
    parse_mysql_datetime,
    quote_mysql_identifier,
    room_table_name,
    read_frame,
    fetch_room_status,
)


class DouyuProtocolTests(unittest.TestCase):
    def test_encode_and_decode_fields_round_trip_escapes_special_chars(self):
        fields = {
            "type": "chatmsg",
            "nn": "a@b",
            "txt": "hello/world",
        }

        encoded = encode_fields(fields)
        self.assertEqual(encoded, "type@=chatmsg/nn@=a@Ab/txt@=hello@Sworld/")
        self.assertEqual(decode_fields(encoded), fields)

    def test_pack_message_can_be_read_back_from_socket_pair(self):
        left, right = socket.socketpair()
        try:
            left.sendall(pack_message("type@=chatmsg/nn@=tester/txt@=hi/"))
            self.assertEqual(read_frame(right), "type@=chatmsg/nn@=tester/txt@=hi/")
        finally:
            left.close()
            right.close()

    def test_parse_mysql_datetime_returns_naive_utc_datetime(self):
        parsed = parse_mysql_datetime("2026-06-01T07:59:04.690948+00:00")
        self.assertEqual(parsed, datetime(2026, 6, 1, 7, 59, 4, 690948))
        self.assertIsNone(parsed.tzinfo)

    def test_quote_mysql_identifier_rejects_backticks(self):
        self.assertEqual(quote_mysql_identifier("danmu_messages"), "`danmu_messages`")
        with self.assertRaises(ValueError):
            quote_mysql_identifier("bad`table")

    def test_room_table_name_uses_room_id(self):
        self.assertEqual(room_table_name("4767111"), "danmu_room_4767111")
        with self.assertRaises(ValueError):
            room_table_name("4767111;drop")


if __name__ == "__main__":
    unittest.main()


class RoomStatusTests(unittest.TestCase):
    def test_room_status_helper_is_exported(self):
        self.assertTrue(callable(fetch_room_status))
