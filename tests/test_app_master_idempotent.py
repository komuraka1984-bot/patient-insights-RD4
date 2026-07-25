import importlib
import os
import unittest

os.environ.pop("DATABASE_URL", None)
os.environ["MASTER_DB_REQUIRED"] = "false"

import app as legacy
import app_master


def closure_value(function, name):
    values = dict(
        zip(
            function.__code__.co_freevars,
            (cell.cell_contents for cell in function.__closure__ or ()),
        )
    )
    return values.get(name)


class AppMasterIdempotenceTest(unittest.TestCase):
    def test_rerun_does_not_wrap_previous_wrapper(self):
        importlib.reload(app_master)
        first_wrapper = legacy.render_adct
        original = legacy._master_original_render_adct

        self.assertIs(closure_value(first_wrapper, "original_renderer"), original)
        self.assertIs(app_master._original_save_result, legacy._master_original_save_result)

        importlib.reload(app_master)
        second_wrapper = legacy.render_adct

        self.assertIsNot(second_wrapper, first_wrapper)
        self.assertIs(closure_value(second_wrapper, "original_renderer"), original)
        self.assertIs(app_master._original_save_result, legacy._master_original_save_result)


if __name__ == "__main__":
    unittest.main()
