"""LivingColor Plugin — Multi-Agent Delivery for Hermes (Text-only, no LaTeX)."""
from manim import *

BG = "#1C1C1C"
PRIMARY = "#58C4DD"
SECONDARY = "#83C167"
ACCENT = "#FFFF00"
PURPLE = "#BB86FC"
ORANGE = "#FF8A65"
RED = "#FF5252"
GRAY = "#888888"
MONO = "Menlo"


# ═════════════════════════════════════════════════════════════════
# Scene 1 — Plugin Connected to Hermes (6s)
# ═════════════════════════════════════════════════════════════════
class Scene1_PluginConnection(Scene):
    def construct(self):
        self.camera.background_color = BG

        # Hermes "shell" frame
        shell = Rectangle(
            width=6.5, height=4.0,
            color=GRAY, stroke_width=2, stroke_opacity=0.4,
            fill_color=BG, fill_opacity=1,
        ).to_edge(UP, buff=1.0)

        shell_label = Text("HERMES", font_size=20, font=MONO,
                           color=GRAY, weight=BOLD)
        shell_label.next_to(shell, UP, buff=0.15)

        self.play(
            Create(shell, run_time=1.0),
            FadeIn(shell_label, run_time=0.8),
        )
        self.wait(0.3)

        # LivingColor tab inside shell
        lc_box = RoundedRectangle(
            width=3.2, height=1.8,
            corner_radius=0.15,
            color=PRIMARY, stroke_width=3,
            fill_color=PRIMARY, fill_opacity=0.1,
        )
        lc_box.move_to(shell.get_center())

        lc_title = Text("LivingColor", font_size=28, font=MONO,
                        color=PRIMARY, weight=BOLD)
        lc_title.move_to(lc_box.get_center()).shift(UP * 0.15)

        lc_sub = Text("Plugin", font_size=20, font=MONO,
                      color=PRIMARY, weight=BOLD)
        lc_sub.next_to(lc_title, DOWN, buff=0.15)

        # Arrow from Hermes shell to plugin
        arrow_in = Arrow(
            shell.get_right() + LEFT * 1.2 + UP * 0.5,
            lc_box.get_right() + RIGHT * 0.3,
            color=SECONDARY, stroke_width=4, max_tip_length_to_length_ratio=0.1,
        )

        self.play(
            FadeIn(lc_box, run_time=1.0),
            Write(lc_title, run_time=0.8),
            Write(lc_sub, run_time=0.6),
            Create(arrow_in, run_time=0.8),
        )

        self.add_subcaption("LivingColor plugin runs inside Hermes", duration=2)
        self.wait(2.0)
        self.play(FadeOut(Group(*self.mobjects)), run_time=0.5)


# ═════════════════════════════════════════════════════════════════
# Scene 2 — Agent Hierarchy (12s)
# ═════════════════════════════════════════════════════════════════
class Scene2_AgentHierarchy(Scene):
    def construct(self):
        self.camera.background_color = BG

        # --- Title ---
        title = Text("Multi-Agent Architecture", font_size=36, font=MONO,
                     color=PRIMARY, weight=BOLD)
        title.to_edge(UP, buff=0.5)
        self.play(Write(title), run_time=1.2)
        self.wait(0.8)

        # --- Orchestrator node (top) ---
        orch_box = RoundedRectangle(
            width=3.6, height=1.0, corner_radius=0.12,
            color=ORANGE, stroke_width=3,
            fill_color=ORANGE, fill_opacity=0.15,
        )
        orch_box.next_to(title, DOWN, buff=0.8)
        orch_label = Text("Orchestrator", font_size=24, font=MONO,
                          color=ORANGE, weight=BOLD)
        orch_label.move_to(orch_box.get_center()).shift(UP * 0.08)
        orch_desc = Text("Decomposes & Routes", font_size=14, font=MONO,
                         color=ORANGE, weight=BOLD)
        orch_desc.next_to(orch_label, DOWN, buff=0.08)

        self.play(
            FadeIn(orch_box, run_time=0.8),
            Write(orch_label, run_time=0.7),
            Write(orch_desc, run_time=0.5),
        )
        self.wait(0.6)

        # --- Worker nodes (row of 3) ---
        workers = [
            ("bibnum-analyst", "Jira Analysis", PURPLE),
            ("bibnum-dev", "Development", PRIMARY),
            ("reviewer", "Code Review", SECONDARY),
        ]

        worker_boxes = []
        worker_labels = []
        worker_descs = []
        for i, (name, desc, color) in enumerate(workers):
            box = RoundedRectangle(
                width=2.2, height=0.85, corner_radius=0.1,
                color=color, stroke_width=2.5,
                fill_color=color, fill_opacity=0.12,
            )
            box.next_to(orch_box, DOWN, buff=1.2)
            box.shift((i - 1) * 2.5 * RIGHT)

            label = Text(name, font_size=18, font=MONO,
                        color=color, weight=BOLD)
            label.move_to(box.get_center()).shift(UP * 0.08)

            sub = Text(desc, font_size=12, font=MONO,
                      color=color)
            sub.next_to(label, DOWN, buff=0.06)

            worker_boxes.append(box)
            worker_labels.append(label)
            worker_descs.append(sub)

        # Arrows from orchestrator to workers
        arrows = []
        for wb in worker_boxes:
            arr = Arrow(
                orch_box.get_bottom(),
                wb.get_top(),
                color=GRAY, stroke_width=2,
                max_tip_length_to_length_ratio=0.08,
                buff=0.15,
            )
            arrows.append(arr)

        # Animate all workers + arrows
        anims = []
        for i in range(3):
            anims.append(FadeIn(worker_boxes[i], run_time=0.6))
            anims.append(Write(worker_labels[i], run_time=0.5))
            anims.append(Write(worker_descs[i], run_time=0.4))
            anims.append(Create(arrows[i], run_time=0.5))

        self.play(*anims, run_time=2.5)
        self.wait(1.2)

        # --- Kanban Board label ---
        kb_label = Text("Kanban Board", font_size=20, font=MONO,
                        color=ACCENT, weight=BOLD)
        kb_label.next_to(worker_boxes[0], DOWN, buff=1.0)
        kb_rect = SurroundingRectangle(
            Group(*worker_boxes), color=ACCENT,
            stroke_width=1.5, stroke_opacity=0.4,
            buff=0.5,
        )

        self.play(
            FadeIn(kb_label, run_time=0.7),
            Create(kb_rect, run_time=0.7),
        )
        self.add_subcaption("One orchestrator dispatches to specialist agents", duration=2.5)
        self.wait(2.5)
        self.play(FadeOut(Group(*self.mobjects)), run_time=0.5)


# ═════════════════════════════════════════════════════════════════
# Scene 3 — External Coding Agents (8s)
# ═════════════════════════════════════════════════════════════════
class Scene3_ExternalAgents(Scene):
    def construct(self):
        self.camera.background_color = BG

        # Title
        title = Text("External Coding Agents", font_size=36, font=MONO,
                     color=PRIMARY, weight=BOLD)
        title.to_edge(UP, buff=0.5)
        self.play(Write(title), run_time=1.0)
        self.wait(0.5)

        # Worker box (source)
        worker_box = RoundedRectangle(
            width=2.2, height=0.9, corner_radius=0.1,
            color=PRIMARY, stroke_width=2.5,
            fill_color=PRIMARY, fill_opacity=0.12,
        )
        worker_box.shift(UP * 0.2 + LEFT * 2.5)
        worker_label = Text("bibnum-dev", font_size=20, font=MONO,
                           color=PRIMARY, weight=BOLD)
        worker_label.move_to(worker_box.get_center())
        worker_sub = Text("Hermes Worker", font_size=12, font=MONO,
                         color=PRIMARY)
        worker_sub.next_to(worker_label, DOWN, buff=0.06)

        self.play(
            FadeIn(worker_box, run_time=0.6),
            Write(worker_label, run_time=0.6),
            Write(worker_sub, run_time=0.4),
        )
        self.wait(0.4)

        # External agents (3)
        externals = [
            ("Claude Code", PURPLE),
            ("Codex CLI", SECONDARY),
            ("OpenCode", ORANGE),
        ]

        ext_boxes = []
        ext_labels = []
        ext_arrows = []
        for i, (name, color) in enumerate(externals):
            box = RoundedRectangle(
                width=2.0, height=0.7, corner_radius=0.1,
                color=color, stroke_width=2.5,
                fill_color=color, fill_opacity=0.12,
            )
            box.next_to(worker_box, RIGHT, buff=0.6)
            box.shift((i - 1) * 1.2 * DOWN)

            label = Text(name, font_size=18, font=MONO,
                        color=color, weight=BOLD)
            label.move_to(box.get_center())

            arr = Arrow(
                worker_box.get_right(),
                box.get_left(),
                color=color, stroke_width=2,
                max_tip_length_to_length_ratio=0.08,
                buff=0.12,
            )

            ext_boxes.append(box)
            ext_labels.append(label)
            ext_arrows.append(arr)

        # "Delegates to" label
        del_label = Text("delegates to", font_size=14, font=MONO,
                         color=GRAY)
        del_label.next_to(worker_box, RIGHT, buff=0.15).shift(UP * 1.4)

        for i in range(3):
            self.play(
                FadeIn(ext_boxes[i], run_time=0.5),
                Write(ext_labels[i], run_time=0.4),
                Create(ext_arrows[i], run_time=0.4),
            )
            self.wait(0.15)

        self.play(FadeIn(del_label, run_time=0.6))
        self.add_subcaption("Workers can delegate to external coding agents", duration=2.5)
        self.wait(2.5)
        self.play(FadeOut(Group(*self.mobjects)), run_time=0.5)


# ═════════════════════════════════════════════════════════════════
# Scene 4 — Full Autonomous Pipeline (9s)
# ═════════════════════════════════════════════════════════════════
class Scene4_FullPipeline(Scene):
    def construct(self):
        self.camera.background_color = BG

        # Title
        title = Text("Fully Autonomous Delivery", font_size=36, font=MONO,
                     color=PRIMARY, weight=BOLD)
        title.to_edge(UP, buff=0.5)
        self.play(Write(title), run_time=1.0)
        self.wait(0.5)

        # Pipeline steps
        steps = [
            ("Cron\n  9AM", ORANGE),
            ("Orche-\nstrator", ORANGE),
            ("Analyst\ndeepseek", PURPLE),
            ("Dev\nkimi", PRIMARY),
            ("GitLab\nMR", SECONDARY),
        ]

        step_boxes = []
        step_labels = []
        for i, (label, color) in enumerate(steps):
            box = RoundedRectangle(
                width=1.6, height=0.9, corner_radius=0.1,
                color=color, stroke_width=2.5,
                fill_color=color, fill_opacity=0.1,
            )
            box.shift(UP * 0.3 + (i - 2) * 2.0 * RIGHT)
            lbl = Text(label, font_size=15, font=MONO,
                      color=color, weight=BOLD, line_spacing=0.9)
            lbl.move_to(box.get_center())
            step_boxes.append(box)
            step_labels.append(lbl)

        # Show all boxes grey first
        ghost_boxes = VGroup(*[
            box.copy().set_stroke(color=GRAY, opacity=0.3)
            .set_fill(color=GRAY, opacity=0.05)
            for box in step_boxes
        ])

        self.play(FadeIn(ghost_boxes, run_time=0.8))
        self.wait(0.3)

        # Animate each step sequentially with arrows
        for i in range(len(step_boxes)):
            self.play(
                Transform(ghost_boxes[i], step_boxes[i], run_time=0.5),
                Write(step_labels[i], run_time=0.4),
            )

            if i < len(step_boxes) - 1:
                arr = Arrow(
                    step_boxes[i].get_right(),
                    step_boxes[i + 1].get_left(),
                    color=ACCENT, stroke_width=3,
                    max_tip_length_to_length_ratio=0.08,
                    buff=0.15,
                )
                self.play(Create(arr, run_time=0.35))
                self.add(arr)

            self.wait(0.25)

        # Jira icon at left
        jira_label = Text("Jira ticket", font_size=12, font=MONO,
                         color=ORANGE)
        jira_label.next_to(step_boxes[0], UP, buff=0.2)
        self.play(FadeIn(jira_label, run_time=0.5))

        self.add_subcaption("From Jira ticket to merged PR — zero human touch", duration=3.0)
        self.wait(3.0)
        self.play(FadeOut(Group(*self.mobjects)), run_time=0.5)
