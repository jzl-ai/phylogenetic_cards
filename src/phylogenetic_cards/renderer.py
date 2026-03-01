"""Pillow-based card image renderer for phylogenetic cards."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from .models import CardContent


@dataclass
class CardStyle:
    # Large Tarot: 89x127mm at 300 DPI
    width: int = 1051
    height: int = 1500
    dpi: int = 300

    # Colors
    bg_color: str = "#FFFFF0"  # ivory
    accent_color: str = "#2D5F2D"  # forest green
    text_color: str = "#1A1A1A"
    muted_color: str = "#666666"
    divider_color: str = "#2D5F2D"

    # Margins (pixels)
    margin_x: int = 60
    margin_top: int = 80
    margin_bottom: int = 60

    # Font sizes
    latin_name_size: int = 52
    common_name_size: int = 38
    rank_size: int = 28
    body_size: int = 26
    heading_size: int = 30
    mya_size: int = 32
    small_size: int = 22


class CardRenderer:
    def __init__(self, style: CardStyle | None = None) -> None:
        self.style = style or CardStyle()
        self._load_fonts()

    def _load_fonts(self) -> None:
        s = self.style
        # Try system fonts, fall back to default
        try:
            self.font_latin = ImageFont.truetype("Times New Roman Bold", s.latin_name_size)
            self.font_common = ImageFont.truetype("Helvetica", s.common_name_size)
            self.font_rank = ImageFont.truetype("Helvetica", s.rank_size)
            self.font_body = ImageFont.truetype("Helvetica", s.body_size)
            self.font_heading = ImageFont.truetype("Helvetica Bold", s.heading_size)
            self.font_mya = ImageFont.truetype("Helvetica Bold", s.mya_size)
            self.font_small = ImageFont.truetype("Helvetica", s.small_size)
        except OSError:
            self.font_latin = ImageFont.load_default(s.latin_name_size)
            self.font_common = ImageFont.load_default(s.common_name_size)
            self.font_rank = ImageFont.load_default(s.rank_size)
            self.font_body = ImageFont.load_default(s.body_size)
            self.font_heading = ImageFont.load_default(s.heading_size)
            self.font_mya = ImageFont.load_default(s.mya_size)
            self.font_small = ImageFont.load_default(s.small_size)

    def render_front(
        self,
        card: CardContent,
        illustration: Image.Image | None = None,
        tree_diagram: Image.Image | None = None,
    ) -> Image.Image:
        s = self.style
        img = Image.new("RGB", (s.width, s.height), s.bg_color)
        draw = ImageDraw.Draw(img)

        # Top accent bar
        draw.rectangle([0, 0, s.width, 12], fill=s.accent_color)

        # Rank label at top
        y = s.margin_top
        rank_text = card.front.rank.upper()
        bbox = draw.textbbox((0, 0), rank_text, font=self.font_rank)
        text_w = bbox[2] - bbox[0]
        draw.text(
            ((s.width - text_w) / 2, y),
            rank_text,
            fill=s.accent_color,
            font=self.font_rank,
        )
        y += 60

        # Divider line
        draw.line(
            [(s.margin_x + 40, y), (s.width - s.margin_x - 40, y)],
            fill=s.divider_color, width=2,
        )
        y += 40

        # Latin name (large, centered, italic feel)
        latin_text = card.front.latin_name
        lines = self._wrap_text(draw, latin_text, self.font_latin, s.width - 2 * s.margin_x)
        for line in lines:
            bbox = draw.textbbox((0, 0), line, font=self.font_latin)
            text_w = bbox[2] - bbox[0]
            draw.text(
                ((s.width - text_w) / 2, y),
                line,
                fill=s.text_color,
                font=self.font_latin,
            )
            y += bbox[3] - bbox[1] + 16

        y += 20

        # Common name
        common_text = card.front.common_name
        bbox = draw.textbbox((0, 0), common_text, font=self.font_common)
        text_w = bbox[2] - bbox[0]
        draw.text(
            ((s.width - text_w) / 2, y),
            common_text,
            fill=s.muted_color,
            font=self.font_common,
        )
        y += 40

        # -- Organism illustration (centered in middle area) --
        if illustration is not None:
            illust_max_w = s.width - 2 * s.margin_x - 40
            illust_max_h = 550
            illust = illustration.copy()
            illust.thumbnail((illust_max_w, illust_max_h), Image.LANCZOS)
            ix = (s.width - illust.width) // 2
            iy = y + 10
            if illust.mode == "RGBA":
                img.paste(illust, (ix, iy), illust)
            else:
                img.paste(illust, (ix, iy))
            y = iy + illust.height + 10

        # -- Lower section: tree diagram (left) and MYA (right) --
        if tree_diagram is not None:
            lower_y = s.height - s.margin_bottom - 350
            td = tree_diagram.copy()
            td.thumbnail((280, 320), Image.LANCZOS)
            if td.mode == "RGBA":
                img.paste(td, (s.margin_x, lower_y), td)
            else:
                img.paste(td, (s.margin_x, lower_y))

        if card.front.divergence_mya is not None:
            mya_text = f"{card.front.divergence_mya:g} MYA"
            bbox = draw.textbbox((0, 0), mya_text, font=self.font_mya)
            text_w = bbox[2] - bbox[0]

            if tree_diagram is not None:
                # Right-aligned to balance tree diagram
                mya_x = s.width - s.margin_x - text_w
                mya_y = s.height - s.margin_bottom - 200
            else:
                # Centered (original layout)
                mya_x = (s.width - text_w) / 2
                mya_y = s.height - s.margin_bottom - 200

            draw.text(
                (mya_x, mya_y),
                mya_text,
                fill=s.accent_color,
                font=self.font_mya,
            )

            label = "million years ago"
            bbox2 = draw.textbbox((0, 0), label, font=self.font_small)
            text_w2 = bbox2[2] - bbox2[0]
            label_x = mya_x + (text_w - text_w2) / 2
            draw.text(
                (label_x, mya_y + 50),
                label,
                fill=s.muted_color,
                font=self.font_small,
            )

        # Bottom accent bar
        draw.rectangle([0, s.height - 12, s.width, s.height], fill=s.accent_color)

        return img

    def render_back(self, card: CardContent) -> Image.Image:
        s = self.style
        img = Image.new("RGB", (s.width, s.height), s.bg_color)
        draw = ImageDraw.Draw(img)

        # Top accent bar
        draw.rectangle([0, 0, s.width, 12], fill=s.accent_color)

        y = s.margin_top
        content_width = s.width - 2 * s.margin_x

        # Header: common name
        header = card.front.common_name
        bbox = draw.textbbox((0, 0), header, font=self.font_common)
        text_w = bbox[2] - bbox[0]
        draw.text(
            ((s.width - text_w) / 2, y),
            header,
            fill=s.accent_color,
            font=self.font_common,
        )
        y += 60

        # Divider
        draw.line(
            [(s.margin_x, y), (s.width - s.margin_x, y)],
            fill=s.divider_color, width=2,
        )
        y += 30

        # Synapomorphies
        if card.back.synapomorphies:
            draw.text(
                (s.margin_x, y),
                "SYNAPOMORPHIES",
                fill=s.accent_color,
                font=self.font_heading,
            )
            y += 45

            for syn in card.back.synapomorphies:
                bullet = f"\u2022 {syn}"
                lines = self._wrap_text(draw, bullet, self.font_body, content_width - 20)
                for line in lines:
                    draw.text(
                        (s.margin_x + 10, y),
                        line,
                        fill=s.text_color,
                        font=self.font_body,
                    )
                    y += 34
                y += 4

            y += 16

        # Other characters (autapomorphies, plesiomorphies)
        if card.back.other_characters:
            draw.text(
                (s.margin_x, y),
                "OTHER CHARACTERS",
                fill=s.muted_color,
                font=self.font_heading,
            )
            y += 45

            for char in card.back.other_characters:
                bullet = f"\u2022 {char}"
                lines = self._wrap_text(draw, bullet, self.font_body, content_width - 20)
                for line in lines:
                    draw.text(
                        (s.margin_x + 10, y),
                        line,
                        fill=s.text_color,
                        font=self.font_body,
                    )
                    y += 34
                y += 4

            y += 16

        # Representative species
        if card.back.representative_species:
            draw.text(
                (s.margin_x, y),
                "REPRESENTATIVE SPECIES",
                fill=s.accent_color,
                font=self.font_heading,
            )
            y += 45

            for sp in card.back.representative_species:
                bullet = f"\u2022 {sp}"
                lines = self._wrap_text(draw, bullet, self.font_body, content_width - 20)
                for line in lines:
                    draw.text(
                        (s.margin_x + 10, y),
                        line,
                        fill=s.text_color,
                        font=self.font_body,
                    )
                    y += 34
                y += 4

            y += 16

        # Tree context (parent / children)
        draw.line(
            [(s.margin_x, y), (s.width - s.margin_x, y)],
            fill=s.divider_color, width=1,
        )
        y += 20

        if card.back.parent_clade_name:
            parent_text = f"Parent: {card.back.parent_clade_name}"
            draw.text(
                (s.margin_x, y),
                parent_text,
                fill=s.muted_color,
                font=self.font_small,
            )
            y += 30

        if card.back.child_clade_names:
            children_label = "Children: " + ", ".join(card.back.child_clade_names)
            lines = self._wrap_text(draw, children_label, self.font_small, content_width)
            for line in lines:
                draw.text(
                    (s.margin_x, y),
                    line,
                    fill=s.muted_color,
                    font=self.font_small,
                )
                y += 28

        # Bottom accent bar
        draw.rectangle([0, s.height - 12, s.width, s.height], fill=s.accent_color)

        return img

    def render_to_files(
        self,
        card: CardContent,
        output_dir: str | Path,
        illustration: Image.Image | None = None,
        tree_diagram: Image.Image | None = None,
    ) -> tuple[Path, Path]:
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        front_img = self.render_front(card, illustration=illustration, tree_diagram=tree_diagram)
        back_img = self.render_back(card)

        front_path = output_dir / f"{card.clade_id}_front.png"
        back_path = output_dir / f"{card.clade_id}_back.png"

        front_img.save(str(front_path), dpi=(self.style.dpi, self.style.dpi))
        back_img.save(str(back_path), dpi=(self.style.dpi, self.style.dpi))

        return front_path, back_path

    @staticmethod
    def _wrap_text(
        draw: ImageDraw.ImageDraw,
        text: str,
        font: ImageFont.FreeTypeFont,
        max_width: int,
    ) -> list[str]:
        words = text.split()
        lines: list[str] = []
        current = ""
        for word in words:
            test = f"{current} {word}".strip()
            bbox = draw.textbbox((0, 0), test, font=font)
            if bbox[2] - bbox[0] <= max_width:
                current = test
            else:
                if current:
                    lines.append(current)
                current = word
        if current:
            lines.append(current)
        return lines or [text]
