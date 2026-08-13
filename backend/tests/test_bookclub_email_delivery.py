import unittest
from unittest.mock import patch

from bookclub import email_delivery, participant_email_delivery


class BookClubEmailDeliveryTests(unittest.TestCase):
    @patch("bookclub.email_delivery.send_email", return_value=True)
    def test_onboarding_is_branded_multipart_email(self, send_email) -> None:
        sent = email_delivery.send_onboarding_email(
            recipient="reader@example.com",
            subject="Welcome to the club",
            body="Hi Reader,\n\nYour copy is ready.",
            club_name="Mystery Readers",
        )

        self.assertTrue(sent)
        payload = send_email.call_args.kwargs
        self.assertEqual(payload["from_name"], "Book Club by Library Tools")
        self.assertIn("<!doctype html>", payload["html_body"])
        self.assertIn("Your copy is ready.", payload["html_body"])
        self.assertIn("Mystery Readers", payload["html_body"])
        self.assertIn("#173f35", payload["html_body"])
        self.assertIn("#d2713f", payload["html_body"])
        self.assertIn("#e0af65", payload["html_body"])
        self.assertIn("A note from your book club", payload["html_body"])
        self.assertIn("Book Club by Library Tools", payload["text_body"])

    @patch("bookclub.email_delivery.send_email", return_value=True)
    def test_reminders_are_addressed_individually(self, send_email) -> None:
        sent = email_delivery.send_reminder_batch(
            recipients=["one@example.com", "two@example.com"],
            subject="Meeting reminder",
            body="We meet Thursday.",
            club_name="Mystery Readers",
        )

        self.assertTrue(sent)
        self.assertEqual(send_email.call_count, 2)
        self.assertEqual(send_email.call_args_list[0].kwargs["to"], ["one@example.com"])
        self.assertEqual(send_email.call_args_list[1].kwargs["to"], ["two@example.com"])
        self.assertNotIn("bcc", send_email.call_args_list[0].kwargs)
        self.assertIn("Meeting reminder", send_email.call_args.kwargs["html_body"])

    @patch("bookclub.participant_email_delivery.send_email", return_value=True)
    def test_verification_identifies_club_and_destination(self, send_email) -> None:
        participant_email_delivery.send_verification_email(
            recipient="reader@example.com",
            name="Reader <One>",
            club_name="Mystery & More",
            verification_url="https://bookclub.libtools.app/verify-email?token=abc",
        )

        payload = send_email.call_args.kwargs
        self.assertIn("Mystery &amp; More", payload["html_body"])
        self.assertIn("Reader &lt;One&gt;", payload["html_body"])
        self.assertIn("bookclub.libtools.app", payload["html_body"])
        self.assertIn("If you did not create this account", payload["text_body"])

    @patch("bookclub.participant_email_delivery.send_email", return_value=True)
    def test_broadcast_has_visible_and_header_unsubscribe(self, send_email) -> None:
        unsubscribe_url = "https://bookclub.libtools.app/unsubscribe?token=abc"
        participant_email_delivery.send_broadcast_email(
            recipient="reader@example.com",
            subject="Club update",
            body="Next meeting is Thursday.",
            unsubscribe_url=unsubscribe_url,
            club_name="Mystery Readers",
        )

        payload = send_email.call_args.kwargs
        self.assertEqual(
            payload["headers"]["List-Unsubscribe"], f"<{unsubscribe_url}>"
        )
        self.assertIn(unsubscribe_url, payload["text_body"])
        self.assertIn("unsubscribe from club broadcasts", payload["html_body"])


if __name__ == "__main__":
    unittest.main()
