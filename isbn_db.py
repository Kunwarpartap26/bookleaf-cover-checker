"""
isbn_db.py — Mock ISBN → Author + Book metadata mapping
In production, replace with a real database query.
"""

import os

ISBN_DATABASE = {
    "9781234567890": {
        "author_name":  "Ojal Jain",
        "author_email": "ojal@example.com",
        "book_title":   "Whispers of the Soul",
    },
    "9789876543210": {
        "author_name":  "Arjun Mehta",
        "author_email": "arjun@example.com",
        "book_title":   "The Quiet Hours",
    },
    "9781122334455": {
        "author_name":  "Priya Sharma",
        "author_email": "priya@example.com",
        "book_title":   "Between the Monsoons",
    },
    "9780987654321": {
        "author_name":  "Rahul Verma",
        "author_email": "rahul@example.com",
        "book_title":   "Letters Never Sent",
    },
    "9781357924680": {
        "author_name":  "Neha Kapoor",
        "author_email": "neha@example.com",
        "book_title":   "Fragments of Light",
    },
    "9782468013579": {
        "author_name":  "Siddharth Rao",
        "author_email": "siddharth@example.com",
        "book_title":   "The Last Garden",
    },
    "9783141592653": {
        "author_name":  "Ananya Singh",
        "author_email": "ananya@example.com",
        "book_title":   "Ink and Silence",
    },
    "9784192837465": {
        "author_name":  "Vikram Nair",
        "author_email": "vikram@example.com",
        "book_title":   "A Thousand Small Fires",
    },
    "9785647382910": {
        "author_name":  "Kavita Iyer",
        "author_email": "kavita@example.com",
        "book_title":   "Roots and Rivers",
    },
    "9786758493021": {
        "author_name":  "Deepa Krishnan",
        "author_email": "deepa@example.com",
        "book_title":   "The Unwritten Page",
    },
    "9787293847561": {
        "author_name":  "Aditya Bose",
        "author_email": "aditya@example.com",
        "book_title":   "Shadow of the Banyan",
    },
    "9788364729103": {
        "author_name":  "Meera Pillai",
        "author_email": "meera@example.com",
        "book_title":   "Songs for the Unnamed",
    },
}


def get_author_info(isbn: str) -> dict:
    """
    Return author metadata for the given ISBN.
    Falls back to a default entry using DEFAULT_AUTHOR_EMAIL from .env.
    """
    return ISBN_DATABASE.get(isbn, {
        "author_name":  "Unknown Author",
        "author_email": os.getenv("DEFAULT_AUTHOR_EMAIL", "test@example.com"),
        "book_title":   "Unknown Title",
    })
