"""Render mini phylogenetic tree diagrams showing a clade in context."""

from __future__ import annotations

from dataclasses import dataclass, field

from PIL import Image, ImageDraw, ImageFont

from .models import Clade


@dataclass
class DiagramStyle:
    width: int = 480
    height: int = 500
    branch_color: str = "#2D5F2D"
    highlight_color: str = "#2D5F2D"
    label_color: str = "#666666"
    line_width: int = 2
    highlight_width: int = 3
    node_radius: int = 5
    font_size: int = 16
    label_font_size: int = 14
    padding: int = 20


@dataclass
class NodePlacement:
    x: int
    y: int
    label: str
    is_focal: bool = False
    label_position: str = "below"  # "above", "below", "right"


@dataclass
class BranchSegment:
    x1: int
    y1: int
    x2: int
    y2: int
    is_highlighted: bool = False
    waypoints: list[tuple[int, int]] = field(default_factory=list)


@dataclass
class LegendEntry:
    key: str  # "A", "B", etc.
    names: list[str]  # clade common names


@dataclass
class VisibleNodes:
    """Which nodes to show in the diagram."""
    ancestors: list[Clade]  # top-to-bottom order (root-most first)
    focal: Clade
    children: list[Clade]
    grandchildren: dict[str, list[Clade]]  # child_id -> grandchildren
    sibling_stubs: dict[str, list[Clade]]  # ancestor_id -> siblings at that level


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
        """Render a mini tree diagram showing clade in phylogenetic context."""
        s = self.style
        img = Image.new("RGBA", (s.width, s.height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)

        visible = self._select_visible_nodes(clade)
        nodes, branches, legend_entries = self._compute_layout(visible)
        self._avoid_overlaps(nodes, branches, draw)
        self._clamp_labels_to_canvas(nodes, draw)
        self._draw(draw, nodes, branches)
        if legend_entries:
            self._draw_legend(draw, nodes, branches, legend_entries)

        return img

    def _select_visible_nodes(self, clade: Clade) -> VisibleNodes:
        """Determine which tree levels to show based on rendezvous proximity."""
        ancestors: list[Clade] = []
        sibling_stubs: dict[str, list[Clade]] = {}

        # Ancestor expansion: walk upward
        if clade.parent is not None:
            # Always show parent
            path = [clade.parent]

            # Walk up to 3 more ancestors looking for a rendezvous node
            current = clade.parent
            for _ in range(3):
                if current.parent is None:
                    break
                current = current.parent
                path.append(current)
                if current.rendezvous_number is not None:
                    break

            # If the clade itself is a rendezvous, show grandparent for context
            if clade.rendezvous_number is not None and clade.parent is not None:
                gp = clade.parent.parent
                if gp is not None and gp not in path:
                    path.append(gp)

            # Reverse to top-down order (root-most first)
            ancestors = list(reversed(path))

            # Collect sibling stubs at each ancestor level
            for anc in ancestors:
                if anc.parent is not None:
                    sibs = [c for c in anc.parent.children if c is not anc]
                    if sibs:
                        sibling_stubs[anc.id] = sibs

            # Also siblings of the focal clade under its parent
            if clade.parent is not None:
                focal_sibs = [c for c in clade.parent.children if c is not clade]
                if focal_sibs:
                    sibling_stubs[clade.id] = focal_sibs

        # Children
        children = list(clade.children)

        # Grandchildren: show if focal is a rendezvous or any child is a rendezvous
        grandchildren: dict[str, list[Clade]] = {}
        show_grandchildren = (
            clade.rendezvous_number is not None
            or any(c.rendezvous_number is not None for c in children)
        )
        if show_grandchildren:
            for child in children:
                if child.children:
                    grandchildren[child.id] = list(child.children)

        return VisibleNodes(
            ancestors=ancestors,
            focal=clade,
            children=children,
            grandchildren=grandchildren,
            sibling_stubs=sibling_stubs,
        )

    def _compute_layout(self, visible: VisibleNodes) -> tuple[list[NodePlacement], list[BranchSegment], list[LegendEntry]]:
        """Allocate (x, y) positions for visible nodes and compute branches."""
        s = self.style
        nodes: list[NodePlacement] = []
        branches: list[BranchSegment] = []
        legend_entries: list[LegendEntry] = []
        next_key_idx = 0

        usable_h = s.height - 2 * s.padding
        x_center = s.width // 2  # centered focal lineage

        # Count vertical levels
        n_ancestor_levels = len(visible.ancestors)
        has_children = len(visible.children) > 0
        has_grandchildren = len(visible.grandchildren) > 0
        n_levels = n_ancestor_levels + 1 + (1 if has_children else 0) + (1 if has_grandchildren else 0)
        level_spacing = usable_h // max(n_levels, 2)

        # Assign y positions per level
        y_positions: list[int] = []
        for i in range(n_levels):
            y_positions.append(s.padding + 20 + i * level_spacing)

        level_idx = 0

        # --- Ancestor levels ---
        prev_x = x_center
        ancestor_positions: list[tuple[int, int]] = []  # (x, y) for each ancestor
        for i, anc in enumerate(visible.ancestors):
            y = y_positions[level_idx]
            ax = x_center  # ancestors stay on focal column

            label = self._truncate(anc.common_name, 40)
            label_pos = "above" if i == 0 else "right"
            nodes.append(NodePlacement(ax, y, label, is_focal=False, label_position=label_pos))
            ancestor_positions.append((ax, y))

            # Sibling stubs at this level — siblings of anc branch from
            # the PARENT (previous ancestor), not from anc itself
            if anc.id in visible.sibling_stubs:
                sibs = visible.sibling_stubs[anc.id]
                sib_x = ax - 70
                if len(sibs) == 1:
                    sib_label = self._truncate(sibs[0].common_name, 40)
                else:
                    key = chr(ord("A") + next_key_idx)
                    next_key_idx += 1
                    sib_label = key
                    legend_entries.append(LegendEntry(key=key, names=[c.common_name for c in sibs]))
                if i > 0:
                    # Branch from the vertical line between parent and this node
                    parent_ay = ancestor_positions[i - 1][1]
                    branch_y = parent_ay + (y - parent_ay) // 2
                else:
                    # Topmost ancestor — parent not shown, branch from self
                    branch_y = y
                nodes.append(NodePlacement(sib_x, branch_y + 20, sib_label, is_focal=False, label_position="below"))
                branches.append(BranchSegment(ax, branch_y, sib_x, branch_y, is_highlighted=False))
                branches.append(BranchSegment(sib_x, branch_y, sib_x, branch_y + 20, is_highlighted=False))

            # Branch from previous ancestor
            if i > 0:
                prev_ax, prev_ay = ancestor_positions[i - 1]
                branches.append(BranchSegment(prev_ax, prev_ay, ax, y, is_highlighted=True))

            level_idx += 1
            prev_x = ax

        # --- Focal level ---
        focal_y = y_positions[level_idx]
        focal_x = x_center
        focal_label = self._truncate(visible.focal.common_name, 40)
        nodes.append(NodePlacement(focal_x, focal_y, focal_label, is_focal=True, label_position="right"))

        # Focal sibling stubs — branch from the parent (last ancestor)
        if visible.focal.id in visible.sibling_stubs:
            sibs = visible.sibling_stubs[visible.focal.id]
            sib_x = focal_x - 70
            if len(sibs) == 1:
                sib_label = self._truncate(sibs[0].common_name, 40)
            else:
                key = chr(ord("A") + next_key_idx)
                next_key_idx += 1
                sib_label = key
                legend_entries.append(LegendEntry(key=key, names=[c.common_name for c in sibs]))
            if ancestor_positions:
                parent_ay = ancestor_positions[-1][1]
                branch_y = parent_ay + (focal_y - parent_ay) // 2
            else:
                branch_y = focal_y
            nodes.append(NodePlacement(sib_x, branch_y + 20, sib_label, is_focal=False, label_position="below"))
            branches.append(BranchSegment(focal_x, branch_y, sib_x, branch_y, is_highlighted=False))
            branches.append(BranchSegment(sib_x, branch_y, sib_x, branch_y + 20, is_highlighted=False))

        # Branch from last ancestor to focal
        if ancestor_positions:
            last_ax, last_ay = ancestor_positions[-1]
            branches.append(BranchSegment(last_ax, last_ay, focal_x, focal_y, is_highlighted=True))

        level_idx += 1

        # --- Children level ---
        if has_children:
            child_y = y_positions[level_idx]
            children = visible.children
            n = len(children)

            # Branch from focal down to child branch point
            child_branch_y = focal_y + (child_y - focal_y) // 3
            branches.append(BranchSegment(focal_x, focal_y, focal_x, child_branch_y, is_highlighted=True))

            if n <= 5:
                max_spacing = 95
                spacing = min(max_spacing, (s.width - 2 * s.padding - 40) // max(n, 1))
                total_w = spacing * (n - 1) if n > 1 else 0
                start_x = focal_x - total_w // 2

                if n > 1:
                    branches.append(BranchSegment(start_x, child_branch_y, start_x + total_w, child_branch_y, is_highlighted=False))

                child_positions: dict[str, tuple[int, int]] = {}
                for i, child in enumerate(children):
                    cx = start_x + i * spacing
                    child_label = self._truncate(child.common_name, 30)
                    nodes.append(NodePlacement(cx, child_y, child_label, is_focal=False, label_position="below"))
                    branches.append(BranchSegment(cx, child_branch_y, cx, child_y, is_highlighted=False))
                    child_positions[child.id] = (cx, child_y)
            else:
                # Fan for many children
                fan_w = min(120, (s.width - 2 * s.padding) // 2 - 20)
                branches.append(BranchSegment(focal_x - fan_w, child_branch_y, focal_x + fan_w, child_branch_y, is_highlighted=False))
                n_stubs = min(7, n)
                stub_spacing = 2 * fan_w // max(n_stubs - 1, 1)
                for i in range(n_stubs):
                    dx = -fan_w + i * stub_spacing
                    branches.append(BranchSegment(focal_x + dx, child_branch_y, focal_x + dx, child_branch_y + 20, is_highlighted=False))

                summary = f"{n} child clades"
                nodes.append(NodePlacement(focal_x, child_y, summary, is_focal=False, label_position="below"))
                child_positions = {}

            level_idx += 1

            # --- Grandchildren level ---
            if has_grandchildren and child_positions:
                gc_y = y_positions[level_idx] if level_idx < len(y_positions) else child_y + level_spacing
                for child_id, gc_list in visible.grandchildren.items():
                    if child_id not in child_positions:
                        continue
                    cx, cy = child_positions[child_id]

                    show_gc = gc_list[:3]
                    n_gc = len(gc_list)
                    if n_gc <= 3:
                        gc_spacing = min(40, 80 // max(len(show_gc), 1))
                        gc_total = gc_spacing * (len(show_gc) - 1) if len(show_gc) > 1 else 0
                        gc_start = cx - gc_total // 2

                        gc_branch_y = cy + (gc_y - cy) // 3
                        branches.append(BranchSegment(cx, cy, cx, gc_branch_y, is_highlighted=False))
                        if len(show_gc) > 1:
                            branches.append(BranchSegment(gc_start, gc_branch_y, gc_start + gc_total, gc_branch_y, is_highlighted=False))

                        for j, gc in enumerate(show_gc):
                            gx = gc_start + j * gc_spacing
                            gc_label = self._truncate(gc.common_name, 25)
                            nodes.append(NodePlacement(gx, gc_y, gc_label, is_focal=False, label_position="below"))
                            branches.append(BranchSegment(gx, gc_branch_y, gx, gc_y, is_highlighted=False))
                    else:
                        gc_branch_y = cy + (gc_y - cy) // 3
                        branches.append(BranchSegment(cx, cy, cx, gc_branch_y, is_highlighted=False))
                        summary = f"({n_gc} spp.)"
                        nodes.append(NodePlacement(cx, gc_y, summary, is_focal=False, label_position="below"))
                        branches.append(BranchSegment(cx, gc_branch_y, cx, gc_y, is_highlighted=False))

        return nodes, branches, legend_entries

    def _avoid_overlaps(
        self,
        nodes: list[NodePlacement],
        branches: list[BranchSegment],
        draw: ImageDraw.ImageDraw,
    ) -> None:
        """Detect and resolve label-label and label-branch overlaps."""
        # Compute text bounding boxes for each node
        bboxes: list[tuple[int, int, int, int]] = []
        for node in nodes:
            font = self.font if node.is_focal else self.font_small
            tb = draw.textbbox((0, 0), node.label, font=font)
            tw = tb[2] - tb[0]
            th = tb[3] - tb[1]

            if node.label_position == "above":
                lx = node.x - tw // 2
                ly = node.y - th - 8
            elif node.label_position == "right":
                lx = node.x + 10
                ly = node.y - th // 2
            else:  # below
                lx = node.x - tw // 2
                ly = node.y + 10

            bboxes.append((lx, ly, lx + tw, ly + th))

        # Check label-label overlaps: shift non-focal to "right" position
        for i in range(len(nodes)):
            for j in range(i + 1, len(nodes)):
                if not self._boxes_overlap(bboxes[i], bboxes[j]):
                    continue
                # Shift the non-focal one
                shift_idx = j if not nodes[j].is_focal else i
                if nodes[shift_idx].is_focal:
                    continue  # don't shift focal
                nodes[shift_idx].label_position = "right"
                # Recompute bbox
                font = self.font if nodes[shift_idx].is_focal else self.font_small
                tb = draw.textbbox((0, 0), nodes[shift_idx].label, font=font)
                tw = tb[2] - tb[0]
                th = tb[3] - tb[1]
                lx = nodes[shift_idx].x + 10
                ly = nodes[shift_idx].y - th // 2
                bboxes[shift_idx] = (lx, ly, lx + tw, ly + th)

        # Check branch-label overlaps: route branches around text
        for b_idx, branch in enumerate(branches):
            for n_idx, bbox in enumerate(bboxes):
                if self._segment_crosses_bbox(branch.x1, branch.y1, branch.x2, branch.y2, bbox):
                    # Add waypoints to route 8px around the text box
                    if branch.x1 == branch.x2:  # vertical branch
                        # Route around the side
                        offset = bbox[2] - branch.x1 + 8 if branch.x1 < bbox[2] else -(branch.x1 - bbox[0] + 8)
                        wx = branch.x1 + offset
                        branch.waypoints = [(wx, branch.y1), (wx, branch.y2)]
                    elif branch.y1 == branch.y2:  # horizontal branch
                        offset = 8
                        wy = bbox[1] - offset if branch.y1 > bbox[1] else bbox[3] + offset
                        branch.waypoints = [(branch.x1, wy), (branch.x2, wy)]

    def _clamp_labels_to_canvas(
        self,
        nodes: list[NodePlacement],
        draw: ImageDraw.ImageDraw,
    ) -> None:
        """Ensure all label text stays within canvas boundaries."""
        s = self.style
        min_x = s.padding
        max_x = s.width - s.padding

        for node in nodes:
            font = self.font if node.is_focal else self.font_small

            for _ in range(30):  # safety limit
                tb = draw.textbbox((0, 0), node.label, font=font)
                tw = tb[2] - tb[0]

                if node.label_position == "right":
                    lx = node.x + 10
                else:  # "above" or "below" — centered on node
                    lx = node.x - tw // 2
                rx = lx + tw

                clipped_left = lx < min_x
                clipped_right = rx > max_x

                if not clipped_left and not clipped_right:
                    break

                # For centered labels clipped on the left, try "right" position
                if (
                    clipped_left
                    and not node.is_focal
                    and node.label_position in ("above", "below")
                ):
                    test_lx = node.x + 10
                    test_rx = test_lx + tw
                    if test_lx >= min_x and test_rx <= max_x:
                        node.label_position = "right"
                        break

                # Truncate label by one character
                if len(node.label) <= 3:
                    break
                if node.label.endswith("\u2026"):
                    node.label = node.label[:-2] + "\u2026"
                else:
                    node.label = node.label[:-1] + "\u2026"

    @staticmethod
    def _boxes_overlap(a: tuple[int, int, int, int], b: tuple[int, int, int, int]) -> bool:
        return a[0] < b[2] and a[2] > b[0] and a[1] < b[3] and a[3] > b[1]

    @staticmethod
    def _segment_crosses_bbox(
        x1: int, y1: int, x2: int, y2: int,
        bbox: tuple[int, int, int, int],
    ) -> bool:
        """Check if an axis-aligned segment crosses a bounding box."""
        bx1, by1, bx2, by2 = bbox
        if x1 == x2:  # vertical
            return bx1 <= x1 <= bx2 and not (max(y1, y2) < by1 or min(y1, y2) > by2)
        if y1 == y2:  # horizontal
            return by1 <= y1 <= by2 and not (max(x1, x2) < bx1 or min(x1, x2) > bx2)
        return False

    def _draw(
        self,
        draw: ImageDraw.ImageDraw,
        nodes: list[NodePlacement],
        branches: list[BranchSegment],
    ) -> None:
        """Render branches and nodes onto the canvas."""
        s = self.style

        # Draw branches first (behind nodes)
        for branch in branches:
            color = s.highlight_color if branch.is_highlighted else s.branch_color
            width = s.highlight_width if branch.is_highlighted else s.line_width

            if branch.waypoints:
                points = [(branch.x1, branch.y1)] + branch.waypoints + [(branch.x2, branch.y2)]
                for i in range(len(points) - 1):
                    draw.line(
                        [points[i], points[i + 1]],
                        fill=color, width=width,
                    )
            else:
                draw.line(
                    [(branch.x1, branch.y1), (branch.x2, branch.y2)],
                    fill=color, width=width,
                )

        # Draw nodes
        for node in nodes:
            r = s.node_radius
            color = s.highlight_color if node.is_focal else s.branch_color
            draw.ellipse([node.x - r, node.y - r, node.x + r, node.y + r], fill=color)

            font = self.font if node.is_focal else self.font_small
            text_color = color if node.is_focal else s.label_color
            tb = draw.textbbox((0, 0), node.label, font=font)
            tw = tb[2] - tb[0]
            th = tb[3] - tb[1]

            if node.label_position == "above":
                draw.text((node.x - tw // 2, node.y - th - 8), node.label, fill=text_color, font=font)
            elif node.label_position == "right":
                draw.text((node.x + 10, node.y - th // 2), node.label, fill=text_color, font=font)
            else:  # below
                draw.text((node.x - tw // 2, node.y + 10), node.label, fill=text_color, font=font)

    def _draw_legend(
        self,
        draw: ImageDraw.ImageDraw,
        nodes: list[NodePlacement],
        branches: list[BranchSegment],
        legend_entries: list[LegendEntry],
    ) -> None:
        """Draw a legend box mapping key letters to clade names."""
        s = self.style
        font = self.font_small
        pad = 8
        line_h = 18
        max_text_w = min(s.width // 2 - 2 * pad, 180)

        # Build legend lines with word-wrapping
        legend_lines: list[str] = []
        for entry in legend_entries:
            prefix = f"{entry.key}: "
            tb = draw.textbbox((0, 0), prefix, font=font)
            prefix_w = tb[2] - tb[0]
            indent_chars = len(prefix)

            names_str = ", ".join(entry.names)
            full_text = prefix + names_str

            # Word-wrap the full text
            words = full_text.split()
            current = ""
            first_line = True
            for word in words:
                test = f"{current} {word}".strip()
                tb = draw.textbbox((0, 0), test, font=font)
                tw = tb[2] - tb[0]
                if tw <= max_text_w:
                    current = test
                else:
                    if current:
                        legend_lines.append(current)
                    current = " " * indent_chars + word
                    first_line = False
            if current:
                legend_lines.append(current)

        if not legend_lines:
            return

        # Compute box size
        line_widths = []
        for line in legend_lines:
            tb = draw.textbbox((0, 0), line, font=font)
            line_widths.append(tb[2] - tb[0])
        box_w = max(line_widths) + 2 * pad
        box_h = len(legend_lines) * line_h + 2 * pad

        # Find clear position
        box_x, box_y = self._find_legend_position(draw, nodes, branches, box_w, box_h)

        # Draw box background and border
        draw.rectangle(
            [box_x, box_y, box_x + box_w, box_y + box_h],
            fill=(255, 255, 240, 240),
            outline=s.label_color,
            width=1,
        )

        # Draw text lines
        ty = box_y + pad
        for line in legend_lines:
            draw.text((box_x + pad, ty), line, fill=s.label_color, font=font)
            ty += line_h

    def _find_legend_position(
        self,
        draw: ImageDraw.ImageDraw,
        nodes: list[NodePlacement],
        branches: list[BranchSegment],
        box_w: int,
        box_h: int,
    ) -> tuple[int, int]:
        """Find a canvas position for the legend that avoids tree elements."""
        s = self.style

        # Compute occupied bounding boxes for all tree elements
        occupied: list[tuple[int, int, int, int]] = []
        for node in nodes:
            font = self.font if node.is_focal else self.font_small
            tb = draw.textbbox((0, 0), node.label, font=font)
            tw = tb[2] - tb[0]
            th = tb[3] - tb[1]
            r = s.node_radius
            if node.label_position == "above":
                lx, ly = node.x - tw // 2, node.y - th - 8
            elif node.label_position == "right":
                lx, ly = node.x + 10, node.y - th // 2
            else:
                lx, ly = node.x - tw // 2, node.y + 10
            occupied.append((
                min(lx, node.x - r) - 4,
                min(ly, node.y - r) - 4,
                max(lx + tw, node.x + r) + 4,
                max(ly + th, node.y + r) + 4,
            ))

        for branch in branches:
            pts = [(branch.x1, branch.y1)]
            pts.extend(branch.waypoints)
            pts.append((branch.x2, branch.y2))
            for i in range(len(pts) - 1):
                x1, y1 = pts[i]
                x2, y2 = pts[i + 1]
                occupied.append((
                    min(x1, x2) - 4, min(y1, y2) - 4,
                    max(x1, x2) + 4, max(y1, y2) + 4,
                ))

        # Scan right side at many y positions, then left side
        candidates: list[tuple[int, int]] = []
        right_x = s.width - s.padding - box_w
        left_x = s.padding
        for y_off in range(s.padding, s.height - box_h - s.padding + 1, 15):
            candidates.append((right_x, y_off))
        for y_off in range(s.padding, s.height - box_h - s.padding + 1, 15):
            candidates.append((left_x, y_off))

        for cx, cy in candidates:
            box_bbox = (cx, cy, cx + box_w, cy + box_h)
            if not any(self._boxes_overlap(box_bbox, occ) for occ in occupied):
                return cx, cy

        # Fallback: bottom-right corner
        return right_x, s.height - s.padding - box_h

    @staticmethod
    def _truncate(text: str, max_len: int) -> str:
        return text if len(text) <= max_len else text[: max_len - 1] + "\u2026"
