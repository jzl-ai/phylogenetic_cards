"""Render mini phylogenetic tree diagrams showing a clade in context."""

from __future__ import annotations

from dataclasses import dataclass

from PIL import Image, ImageDraw, ImageFont

from .models import Clade


@dataclass
class DiagramStyle:
    width: int = 280
    height: int = 400
    branch_color: str = "#2D5F2D"
    highlight_color: str = "#2D5F2D"
    label_color: str = "#666666"
    line_width: int = 2
    highlight_width: int = 3
    node_radius: int = 5
    font_size: int = 16
    label_font_size: int = 14
    padding: int = 20


class TreeDiagramRenderer:
    """Renders a compact cladogram for a single clade's context."""

    def __init__(self, style: DiagramStyle | None = None) -> None:
        self.style = style or DiagramStyle()
        self._load_fonts()

    def _load_fonts(self) -> None:
        try:
            self.font = ImageFont.truetype("Helvetica", self.style.font_size)
            self.font_small = ImageFont.truetype("Helvetica", self.style.label_font_size)
        except OSError:
            self.font = ImageFont.load_default(self.style.font_size)
            self.font_small = ImageFont.load_default(self.style.label_font_size)

    def render(self, clade: Clade) -> Image.Image:
        """Render a mini tree diagram showing parent, this clade, and children."""
        s = self.style
        img = Image.new("RGBA", (s.width, s.height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)

        has_parent = clade.parent is not None
        children = clade.children
        siblings = []
        if clade.parent:
            siblings = [c for c in clade.parent.children if c is not clade]

        # Vertical positions for three levels
        y_parent = s.padding + 20
        y_self = s.height // 2 - 20
        y_children = s.height - s.padding - 30
        x_center = s.width // 2

        # -- Parent level --
        if has_parent:
            parent_label = self._truncate(clade.parent.common_name, 20)
            self._draw_node_label(
                draw, x_center, y_parent, parent_label,
                highlighted=False, label_above=True,
            )

            branch_y = (y_parent + y_self) // 2 + 10
            # Vertical line from parent down to branch point
            draw.line(
                [(x_center, y_parent + 12), (x_center, branch_y)],
                fill=s.branch_color, width=s.line_width,
            )

            if siblings:
                sib_x = x_center - 60
                self_x = x_center + 30
                # Horizontal branch
                draw.line(
                    [(sib_x, branch_y), (self_x, branch_y)],
                    fill=s.branch_color, width=s.line_width,
                )
                # Sibling stub
                draw.line(
                    [(sib_x, branch_y), (sib_x, branch_y + 15)],
                    fill=s.branch_color, width=s.line_width,
                )
                if len(siblings) == 1:
                    sib_label = self._truncate(siblings[0].common_name, 15)
                else:
                    sib_label = f"({len(siblings)} others)"
                self._draw_text_centered(
                    draw, sib_x, branch_y + 18, sib_label,
                    self.font_small, s.label_color,
                )
                # Line down to self
                draw.line(
                    [(self_x, branch_y), (self_x, y_self - 12)],
                    fill=s.highlight_color, width=s.highlight_width,
                )
                self_x_pos = self_x
            else:
                draw.line(
                    [(x_center, branch_y), (x_center, y_self - 12)],
                    fill=s.highlight_color, width=s.highlight_width,
                )
                self_x_pos = x_center
        else:
            self_x_pos = x_center

        # -- This clade (highlighted) --
        self_label = self._truncate(clade.common_name, 22)
        self._draw_node_label(
            draw, self_x_pos, y_self, self_label, highlighted=True,
        )

        # -- Children level --
        if children:
            child_branch_y = y_self + 30
            draw.line(
                [(self_x_pos, y_self + 12), (self_x_pos, child_branch_y)],
                fill=s.highlight_color, width=s.highlight_width,
            )

            n = len(children)
            if n <= 3:
                spacing = min(80, (s.width - 2 * s.padding) // max(n, 1))
                total_w = spacing * (n - 1) if n > 1 else 0
                start_x = self_x_pos - total_w // 2

                if n > 1:
                    draw.line(
                        [(start_x, child_branch_y), (start_x + total_w, child_branch_y)],
                        fill=s.branch_color, width=s.line_width,
                    )

                for i, child in enumerate(children):
                    cx = start_x + i * spacing
                    draw.line(
                        [(cx, child_branch_y), (cx, y_children - 10)],
                        fill=s.branch_color, width=s.line_width,
                    )
                    child_label = self._truncate(child.common_name, 12)
                    self._draw_text_centered(
                        draw, cx, y_children, child_label,
                        self.font_small, s.branch_color,
                    )
            else:
                # Summarize many children
                fan_w = 60
                draw.line(
                    [(self_x_pos - fan_w, child_branch_y),
                     (self_x_pos + fan_w, child_branch_y)],
                    fill=s.branch_color, width=s.line_width,
                )
                # Fan lines
                for dx in [-fan_w, -fan_w // 2, 0, fan_w // 2, fan_w]:
                    draw.line(
                        [(self_x_pos + dx, child_branch_y),
                         (self_x_pos + dx, child_branch_y + 20)],
                        fill=s.branch_color, width=s.line_width,
                    )
                summary = f"{n} child clades"
                self._draw_text_centered(
                    draw, self_x_pos, y_children, summary,
                    self.font_small, s.label_color,
                )

        return img

    def _draw_node_label(
        self,
        draw: ImageDraw.ImageDraw,
        x: int,
        y: int,
        label: str,
        highlighted: bool,
        label_above: bool = False,
    ) -> None:
        s = self.style
        r = s.node_radius
        color = s.highlight_color if highlighted else s.branch_color
        draw.ellipse([x - r, y - r, x + r, y + r], fill=color)

        font = self.font if highlighted else self.font_small
        text_color = color if highlighted else s.label_color
        if label_above:
            self._draw_text_centered(draw, x, y - 22, label, font, text_color)
        else:
            self._draw_text_centered(draw, x, y + 10, label, font, text_color)

    def _draw_text_centered(
        self,
        draw: ImageDraw.ImageDraw,
        x: int,
        y: int,
        text: str,
        font: ImageFont.FreeTypeFont,
        color: str,
    ) -> None:
        bbox = draw.textbbox((0, 0), text, font=font)
        tw = bbox[2] - bbox[0]
        draw.text((x - tw // 2, y), text, fill=color, font=font)

    @staticmethod
    def _truncate(text: str, max_len: int) -> str:
        return text if len(text) <= max_len else text[: max_len - 1] + "\u2026"
