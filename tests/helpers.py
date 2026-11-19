"""Dữ liệu và đối tượng giả dùng chung cho các bài kiểm thử."""
from __future__ import annotations

from pathlib import Path

from content_robot.wordpress import parse_post

FIX = Path(__file__).parent / "fixtures"


class FakeWP:
    def __init__(self, post: dict, products: list):
        self.post, self.products = post, products

    def list_posts(self, **kw):
        return [parse_post(self.post)]

    def get_post(self, wp_id):
        return parse_post(self.post)

    def list_products(self):
        return self.products
