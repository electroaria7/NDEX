import unittest

from ndex_frame.core.geometry import build_render_plan, project_render_plan, resolve_canvas
from ndex_frame.core.models import AspectRatio, OutputSizing


class GeometryTests(unittest.TestCase):
    def test_fixed_width_3_by_4_is_1080_by_1440(self) -> None:
        size = resolve_canvas(OutputSizing("fixed_width", width=1080), AspectRatio(3, 4))
        self.assertEqual(size, (1080, 1440))

    def test_landscape_fits_without_crop(self) -> None:
        plan = build_render_plan((6000, 4000), (1080, 1440), 1.0, 0.0, 0.0)
        self.assertEqual((plan.photo_width, plan.photo_height), (1080, 720))
        self.assertEqual((plan.left, plan.top), (0, 360))

    def test_five_by_seven_portrait_gets_side_margins(self) -> None:
        plan = build_render_plan((5000, 7000), (1080, 1440), 1.0, 0.0, 0.0)
        self.assertEqual(plan.photo_height, 1440)
        self.assertEqual(plan.left, (1080 - plan.photo_width) // 2)

    def test_normalized_position_is_clamped_to_no_crop_bounds(self) -> None:
        plan = build_render_plan((6000, 4000), (1080, 1440), 1.0, 0.0, 2.0)
        self.assertEqual(plan.top + plan.photo_height, 1440)

    def test_photo_scale_bounds_are_enforced(self) -> None:
        with self.assertRaises(ValueError):
            build_render_plan((100, 100), (100, 100), 0.09, 0.0, 0.0)
        with self.assertRaises(ValueError):
            build_render_plan((100, 100), (100, 100), 1.01, 0.0, 0.0)

    def test_canvas_modes_use_half_up_rounding(self) -> None:
        self.assertEqual(resolve_canvas(OutputSizing("fixed_width", width=1), AspectRatio(2, 3)), (1, 2))
        self.assertEqual(resolve_canvas(OutputSizing("fixed_height", height=1), AspectRatio(2, 3)), (1, 1))
        self.assertEqual(resolve_canvas(OutputSizing("long_edge", long_edge=1), AspectRatio(2, 3)), (1, 1))
        self.assertEqual(
            resolve_canvas(OutputSizing("fixed_dimensions", width=7, height=9), AspectRatio(2, 3)),
            (7, 9),
        )

    def test_fit_matrix_preserves_edges_within_one_pixel(self) -> None:
        sources = ((3000, 4000), (5000, 7000), (6000, 4000), (4000, 4000))
        output = (1080, 1440)
        for source in sources:
            output_plan = build_render_plan(source, output, 1.0, 0.37, -0.42)
            for preview_width in (270, 540, 1080):
                preview_height = round(preview_width * output[1] / output[0])
                preview_plan = build_render_plan(source, (preview_width, preview_height), 1.0, 0.37, -0.42)
                scale = output[0] / preview_width
                for output_edge, preview_edge in zip(
                    (output_plan.photo_width, output_plan.photo_height, output_plan.left, output_plan.top),
                    (preview_plan.photo_width, preview_plan.photo_height, preview_plan.left, preview_plan.top),
                ):
                    self.assertLessEqual(abs(output_edge - preview_edge * scale), 1.0, (source, preview_width))

    def test_projection_round_trips_all_edges_without_integer_recalculation(self) -> None:
        sources = ((3000, 4000), (5000, 7000), (6000, 4000), (4000, 4000))
        positions = ((0.0, 0.0), (-1.0, -1.0), (1.0, 1.0), (-0.94, -1.0), (0.94, 1.0))
        output = (1080, 1440)
        for source in sources:
            for x, y in positions:
                plan = build_render_plan(source, output, 1.0, x, y)
                for viewport in ((271, 360), (270, 361)):
                    projected = project_render_plan(plan, viewport)
                    output_edges = (plan.left, plan.top, plan.left + plan.photo_width, plan.top + plan.photo_height)
                    preview_edges = (
                        projected.photo_left,
                        projected.photo_top,
                        projected.photo_right,
                        projected.photo_bottom,
                    )
                    for edge_index, (expected, actual) in enumerate(zip(output_edges, preview_edges)):
                        canvas_offset = projected.canvas_left if edge_index in (0, 2) else projected.canvas_top
                        recovered = (actual - canvas_offset) / projected.scale
                        self.assertLessEqual(abs(expected - recovered), 1.0e-9, (source, x, y, viewport))


if __name__ == "__main__":
    unittest.main()
