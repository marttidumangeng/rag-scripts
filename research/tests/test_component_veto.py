"""The is-this-actually-a-robot gate.

AI verification cannot answer this question — it scores whether a record matches
its source page, so a well-documented depth camera scores exactly like a
well-documented robot. Orbbec (company 1799) reached To Review at **96** with a
structured-light camera; ADLINK put 36 compute modules in the queue at 85-99.
`component_veto` is the only thing standing between that hardware and the
catalogue, so it needs tests in BOTH directions: real components must be
stopped, and real robots must never be.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

_RESEARCH_DIR = Path(__file__).resolve().parents[1]
if str(_RESEARCH_DIR) not in sys.path:
    sys.path.insert(0, str(_RESEARCH_DIR))

from discover_robots import component_veto  # noqa: E402


# (name, first-sentence description, url) — every one is a REAL row we imported.
COMPONENTS = [
    ("Astra 2", "Astra 2 is a high-accuracy structured light camera (0.6m-8m).",
     "https://www.orbbec.com/products/structured-light-camera/astra-2/"),
    ("Gemini 335", "active and passive stereo Depth+RGB camera for indoor and outdoor.",
     "https://www.orbbec.com/products/stereo-vision-camera/gemini-335/"),
    ("MS200k", "single-line high-precision 2D LiDAR with 12m range.",
     "https://www.orbbec.com/products/lidar/ms200k/"),
    ("Persee 2", "compact camera-computer with built-in depth sensing for edge AI.",
     "https://www.orbbec.com/products/camera-computer/persee-2-2/"),
    ("DLAP-211-Orin Nano 4GB", "edge AI inference platform.",
     "https://www.adlinktech.com/Products/Deep_Learning_Accelerator_Platform_and_Server/x"),
    ("RQX-590", "ROS 2 controller for autonomous mobile robots.",
     "https://www.adlinktech.com/Products/ROS2_Solution/ROS2_Controller/x"),
    ("COM-HPC-mMTL", "computer-on-module for embedded systems.",
     "https://www.adlinktech.com/Products/computer_on_modules/COM-HPC/x"),
    ("SBC35-ARL", "single board computer.",
     "https://www.adlinktech.com/Products/Motherboard/SBC35/x"),
]

# Real catalogue robots. A veto here would silently shrink the catalogue, which
# is the more expensive failure — these must stay clean as the pattern grows.
ROBOTS = [
    ("Spot", "Spot is a quadruped robot for industrial inspection.",
     "https://bostondynamics.com/products/spot/"),
    ("UR10e", "UR10e is a collaborative robot arm with 10kg payload.",
     "https://www.universal-robots.com/products/ur10-robot/"),
    ("Jueying Lite3", "Lite3 is a lightweight quadruped robot for research and education.",
     "https://www.deeprobotics.cn/en/index/product1.html"),
    ("PUDU MT1", "MT1 is an autonomous commercial cleaning robot for large venues.",
     "https://www.pudurobotics.com/en/products/mt1"),
    ("Beetle", "Beetle autonomously sweeps industrial floors using AI-driven navigation.",
     "https://gausium.com/products/beetle/"),
    ("Scout Mini", "Scout Mini is a compact UGV platform for research.",
     "https://global.agilex.ai/products/scout-mini"),
    ("LYNX M20", "wheeled-legged robot built for omni-terrain operations.",
     "https://www.deeprobotics.cn/en/index/lynx.html"),
    ("Hotel Robot - W", "room-delivery robot that takes items to guest rooms.",
     "https://www.365robot.sg/hotel-delivery-robot/"),
    ("X30", "X30 is an industrial quadruped robot for inspection and security.",
     "https://www.deeprobotics.cn/en/index/product3.html"),
]


class ComponentVetoTests(unittest.TestCase):
    def test_components_are_vetoed(self):
        for name, desc, url in COMPONENTS:
            with self.subTest(name=name):
                self.assertTrue(component_veto(name, desc, url),
                                f"{name} is a component and must not enter the queue")

    def test_real_robots_pass(self):
        for name, desc, url in ROBOTS:
            with self.subTest(name=name):
                self.assertEqual(component_veto(name, desc, url), "",
                                 f"{name} is a real robot and must not be vetoed")

    def test_url_alone_is_enough(self):
        """The vendor's taxonomy decides even when the copy sounds robotic —
        component marketing always says 'for robotics'."""
        veto = component_veto(
            "Gemini 336L",
            "Long-range depth camera purpose-built for mobile robots and AMRs.",
            "https://www.orbbec.com/products/stereo-vision-camera/gemini-336l/")
        self.assertTrue(veto)

    def test_description_alone_is_enough(self):
        """A component page under an unhelpful URL is still catchable from the
        product's own first sentence."""
        veto = component_veto("VL-2000", "A time-of-flight sensor for navigation.",
                              "https://example.com/p/vl-2000")
        self.assertTrue(veto)

    def test_missing_url_does_not_crash_or_over_veto(self):
        self.assertEqual(component_veto("UR10e", "collaborative robot arm.", ""), "")
        self.assertEqual(component_veto("UR10e", "collaborative robot arm."), "")


if __name__ == "__main__":
    unittest.main()
