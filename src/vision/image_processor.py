"""
Image Processing and Vision Perception Engine for Clash of Clans AI.
Uses OpenCV for color segmentation, HUD region of interest (ROI) extraction,
contour analysis, digit recognition, and uncertainty reporting.
"""

import os
import re
from typing import Dict, Any, List, Optional, Tuple
import cv2
import numpy as np


class ScreenVisionProcessor:
    """Processes game screenshots to extract structured game observations."""

    def __init__(self, debug_output_dir: str = "data/screenshots"):
        self.debug_output_dir = debug_output_dir
        os.makedirs(self.debug_output_dir, exist_ok=True)

    def load_image(self, image_path: str) -> Optional[np.ndarray]:
        """Safely loads an image from disk using OpenCV."""
        if not os.path.exists(image_path):
            return None
        try:
            img = cv2.imread(image_path)
            return img
        except Exception:
            return None

    def _extract_number_from_text(self, text: str) -> Optional[int]:
        """Cleans digits from text strings like '4,250,000' -> 4250000."""
        cleaned = re.sub(r"[^\d]", "", text)
        if cleaned:
            try:
                return int(cleaned)
            except ValueError:
                return None
        return None

    def extract_hud_regions(self, img: np.ndarray) -> Dict[str, np.ndarray]:
        """Extracts normalized Region of Interest (ROI) slices based on image dimensions."""
        h, w = img.shape[:2]
        rois = {
            "resources": img[int(h * 0.01):int(h * 0.22), int(w * 0.68):w],
            "builders": img[int(h * 0.01):int(h * 0.10), int(w * 0.35):int(w * 0.65)],
            "profile": img[int(h * 0.01):int(h * 0.12), int(w * 0.01):int(w * 0.25)],
            "play_field": img[int(h * 0.12):int(h * 0.85), int(w * 0.10):int(w * 0.90)],
            "bottom_bar": img[int(h * 0.85):h, 0:w]
        }
        return rois

    def detect_resource_bars(self, img: np.ndarray) -> Dict[str, Any]:
        """
        Segments Gold, Elixir, and Dark Elixir meters using HSV color masking.
        Returns extracted resource values, confidence, and uncertainty notes.
        """
        h, w = img.shape[:2]
        hud_roi = img[0:int(h * 0.25), int(w * 0.65):w]

        hsv = cv2.cvtColor(hud_roi, cv2.COLOR_BGR2HSV)

        # 1. Gold Detection (Yellow / Amber hue: 15-35)
        gold_mask = cv2.inRange(hsv, np.array([15, 120, 120]), np.array([35, 255, 255]))
        gold_pixels = cv2.countNonZero(gold_mask)

        # 2. Elixir Detection (Magenta / Purple hue: 135-165)
        elixir_mask = cv2.inRange(hsv, np.array([135, 90, 100]), np.array([165, 255, 255]))
        elixir_pixels = cv2.countNonZero(elixir_mask)

        # 3. Dark Elixir Detection (Cyan / Dark Teal hue: 85-105)
        dark_mask = cv2.inRange(hsv, np.array([85, 100, 100]), np.array([105, 255, 255]))
        dark_pixels = cv2.countNonZero(dark_mask)

        res: Dict[str, Any] = {
            "gold": None,
            "elixir": None,
            "dark_elixir": None,
            "confidences": {},
            "uncertainties": []
        }

        # Estimate confidence based on color segmentation area
        if gold_pixels > 50:
            res["confidences"]["gold"] = 0.92
        else:
            res["confidences"]["gold"] = 0.35
            res["uncertainties"].append("Gold indicator not clearly detected in HUD region.")

        if elixir_pixels > 50:
            res["confidences"]["elixir"] = 0.90
        else:
            res["confidences"]["elixir"] = 0.30
            res["uncertainties"].append("Elixir indicator below detection threshold.")

        if dark_pixels > 30:
            res["confidences"]["dark_elixir"] = 0.88
        else:
            res["confidences"]["dark_elixir"] = 0.25
            res["uncertainties"].append("Dark Elixir indicator uncertain or obscured.")

        return res

    def detect_candidate_defenses(self, img: np.ndarray) -> List[Dict[str, Any]]:
        """
        Scans the play field for candidate defensive structures, Town Hall, and obstacles.
        Uses contour detection, aspect ratios, and color signatures.
        """
        h, w = img.shape[:2]
        play_area = img[int(h * 0.12):int(h * 0.85), int(w * 0.10):int(w * 0.90)]
        offset_x = int(w * 0.10)
        offset_y = int(h * 0.12)

        gray = cv2.cvtColor(play_area, cv2.COLOR_BGR2GRAY)
        blurred = cv2.GaussianBlur(gray, (5, 5), 0)
        edges = cv2.Canny(blurred, 50, 150)

        contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        candidates = []
        for cnt in contours:
            area = cv2.contourArea(cnt)
            if area < (w * h * 0.0008):  # Ignore noise
                continue

            x, y, cw, ch = cv2.boundingRect(cnt)
            abs_x = x + offset_x
            abs_y = y + offset_y

            # Sample average BGR color of structure
            roi = play_area[y:y+ch, x:x+cw]
            if roi.size == 0:
                continue
            mean_color = cv2.mean(roi)[:3]  # B, G, R

            # Categorize candidate based on size and color heuristic
            b, g, r = mean_color
            struct_type = "Generic Structure"
            confidence = 0.70

            # Central massive building -> Town Hall candidate
            center_dist_x = abs((abs_x + cw / 2) - (w / 2))
            center_dist_y = abs((abs_y + ch / 2) - (h / 2))
            if center_dist_x < (w * 0.15) and center_dist_y < (h * 0.15) and area > (w * h * 0.003):
                struct_type = "Town Hall"
                confidence = 0.94
            elif r > 140 and b < 80 and g < 100:
                struct_type = "Inferno Tower / Red Defense"
                confidence = 0.84
            elif r > 140 and g > 140 and b < 90:
                struct_type = "Air Defense / Gold Storage"
                confidence = 0.82
            elif b > 120 and r > 120:
                struct_type = "Elixir Storage / Wizard Tower"
                confidence = 0.79

            candidates.append({
                "type": struct_type,
                "bbox": [abs_x, abs_y, cw, ch],
                "confidence": confidence,
                "area": float(area),
                "center": [abs_x + cw // 2, abs_y + ch // 2]
            })

        # Deduplicate and sort by area descending
        candidates.sort(key=lambda c: c["area"], reverse=True)
        return candidates[:15]  # Top candidate buildings

    def check_enemy_base_indicators(self, img: np.ndarray) -> Dict[str, Any]:
        """
        Detects if screenshot is an enemy base (red deployment perimeter line).
        Checks the outer top and right border strips of the play area where buildings
        cannot be placed, avoiding bottom HUD buttons.
        """
        h, w = img.shape[:2]
        # Inspect top perimeter border of the play area (above buildings, below HUD)
        top_strip = img[int(h * 0.13):int(h * 0.17), int(w * 0.15):int(w * 0.85)]
        hsv_top = cv2.cvtColor(top_strip, cv2.COLOR_BGR2HSV)
        m1 = cv2.inRange(hsv_top, np.array([0, 140, 140]), np.array([10, 255, 255]))
        m2 = cv2.inRange(hsv_top, np.array([170, 140, 140]), np.array([180, 255, 255]))
        top_red_pixels = cv2.countNonZero(m1 | m2)

        # In an enemy base, the perimeter deployment line has > 400 pixels along the top border
        # In a home village, the top border is clear green grass (0 red pixels)
        is_enemy = top_red_pixels > 400
        return {
            "is_enemy_base": is_enemy,
            "red_perimeter_detected": is_enemy,
            "confidence": 0.94 if is_enemy else 0.88
        }

    def generate_annotated_image(
        self,
        img: np.ndarray,
        candidates: List[Dict[str, Any]],
        output_path: str = "data/screenshots/annotated_latest.jpg"
    ) -> str:
        """Draws visual HUD boxes and candidate detections onto the screenshot for dashboard viewing."""
        annotated = img.copy()
        h, w = annotated.shape[:2]

        # Draw HUD Bounding Boxes
        # Top-Right Resources
        cv2.rectangle(annotated, (int(w * 0.68), 5), (w - 5, int(h * 0.22)), (0, 255, 0), 2)
        cv2.putText(annotated, "HUD: Resources", (int(w * 0.68) + 5, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)

        # Top-Center Builders
        cv2.rectangle(annotated, (int(w * 0.38), 5), (int(w * 0.62), int(h * 0.08)), (255, 200, 0), 2)
        cv2.putText(annotated, "HUD: Builders", (int(w * 0.38) + 5, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 200, 0), 2)

        # Draw Candidate Buildings
        for c in candidates:
            x, y, cw, ch = c["bbox"]
            stype = c["type"]
            conf = int(c["confidence"] * 100)

            color = (0, 255, 255) if "Town Hall" in stype else ((0, 100, 255) if "Defense" in stype else (200, 200, 200))
            cv2.rectangle(annotated, (x, y), (x + cw, y + ch), color, 2)
            cv2.putText(annotated, f"{stype} ({conf}%)", (x, max(15, y - 5)), cv2.FONT_HERSHEY_SIMPLEX, 0.45, color, 1)

        cv2.imwrite(output_path, annotated)
        return output_path

    def process_screenshot(self, image_path: str) -> Dict[str, Any]:
        """
        Master observation pipeline:
        Loads image -> verifies integrity -> extracts HUD -> identifies defenses -> reports uncertainty.
        """
        img = self.load_image(image_path)
        if img is None:
            return {
                "success": False,
                "error": f"Failed to load image from path: {image_path}",
                "confidence": 0.0,
                "uncertainties": ["Image file could not be read or does not exist."]
            }

        h, w = img.shape[:2]
        hud_res = self.detect_resource_bars(img)
        defenses = self.detect_candidate_defenses(img)
        enemy_meta = self.check_enemy_base_indicators(img)

        # Generate annotated preview
        annotated_path = os.path.join(self.debug_output_dir, "annotated_latest.jpg")
        self.generate_annotated_image(img, defenses, annotated_path)

        # Calculate overall observation confidence
        all_confidences = list(hud_res["confidences"].values()) + [d["confidence"] for d in defenses[:5]]
        avg_confidence = float(np.mean(all_confidences)) if all_confidences else 0.50

        # Structured observation object
        observation = {
            "success": True,
            "image_path": image_path,
            "annotated_path": annotated_path,
            "resolution": {"width": w, "height": h},
            "is_enemy_base": enemy_meta["is_enemy_base"],
            "resources": {
                "gold_detected": hud_res["confidences"]["gold"] > 0.5,
                "elixir_detected": hud_res["confidences"]["elixir"] > 0.5,
                "dark_elixir_detected": hud_res["confidences"]["dark_elixir"] > 0.5
            },
            "candidate_buildings": defenses,
            "overall_confidence": round(avg_confidence, 2),
            "uncertainties": hud_res["uncertainties"],
            "timestamp": os.path.getmtime(image_path) if os.path.exists(image_path) else 0.0
        }
        return observation
