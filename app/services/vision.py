"""Computer Vision, Perceptual Hashing, and Safe Feature Extraction Service."""

import io
import secrets
import string
import logging
from typing import Tuple, Optional
from PIL import Image, ImageOps
import imagehash
import cv2
import numpy as np

logger = logging.getLogger(__name__)

# Allowed MIME and Pillow format mapping
VALID_FORMATS = {
    "JPEG": "jpg",
    "PNG": "png",
    "WEBP": "webp"
}


def generate_public_image_uid(length: int = 8) -> str:
    """
    Generate a cryptographically secure, random public image ID (e.g. IMG-A8K2F9X1).
    Uses Python's secrets module (never pseudo-random).
    """
    # Exclude ambiguous characters (0, O, I, 1) for user clarity
    alphabet = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"
    random_str = "".join(secrets.choice(alphabet) for _ in range(length))
    return f"IMG-{random_str}"


def sanitize_and_strip_exif(image_bytes: bytes) -> Tuple[Image.Image, str]:
    """
    Validate real image content using Pillow, strip all EXIF metadata,
    re-orient image according to EXIF before stripping, and convert to RGB/RGBA.
    Neutralizes polyglot payloads and metadata leaks.

    Returns:
        Tuple of (clean_pil_image, extension)
    Raises:
        ValueError if file is corrupted, unsupported, or exceeds size bounds.
    """
    try:
        raw_stream = io.BytesIO(image_bytes)
        with Image.open(raw_stream) as img:
            img_format = img.format
            if img_format not in VALID_FORMATS:
                raise ValueError(f"Unsupported image format: {img_format}. Allowed: JPEG, PNG, WEBP.")

            # Correct orientation from EXIF before stripping
            try:
                img = ImageOps.exif_transpose(img)
            except Exception:
                pass

            # Convert to standard color space (RGB or RGBA)
            if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
                clean_img = img.convert("RGBA")
                ext = "png"
            else:
                clean_img = img.convert("RGB")
                ext = "jpg" if img_format == "JPEG" else VALID_FORMATS[img_format]

            # Re-create a completely fresh in-memory image without metadata dictionary
            sanitized = Image.frombytes(clean_img.mode, clean_img.size, clean_img.tobytes())

            return sanitized, ext
    except Exception as e:
        if isinstance(e, ValueError):
            raise
        logger.warning("Image sanitization failed: %s", e)
        raise ValueError("Corrupted or invalid image file content.")


def extract_perceptual_hashes(pil_image: Image.Image) -> Tuple[str, str]:
    """
    Extract Perceptual Hash (pHash) and Difference Hash (dHash).
    pHash captures low-frequency DCT components (resilient to compression & scaling).
    dHash captures horizontal gradients.
    """
    phash_val = str(imagehash.phash(pil_image))
    dhash_val = str(imagehash.dhash(pil_image))
    return phash_val, dhash_val


def extract_orb_descriptors(pil_image: Image.Image, max_features: int = 500) -> Optional[bytes]:
    """
    Extract OpenCV ORB keypoints and descriptors from image.
    Descriptors are serialized as raw numpy binary bytes (tobytes()) - NEVER using pickle.

    Returns:
        Raw bytes of uint8 numpy array, or None if no keypoints found.
    """
    try:
        # Convert PIL Image to OpenCV grayscale uint8 numpy array
        np_img = np.array(pil_image.convert("L"))

        orb = cv2.ORB_create(nfeatures=max_features)
        keypoints, descriptors = orb.detectAndCompute(np_img, None)

        if descriptors is None or len(descriptors) == 0:
            logger.info("No ORB keypoints detected in image.")
            return None

        # ORB descriptors are 32 bytes (256 bits) per keypoint, dtype=uint8
        # Serialize safely as raw bytes
        return descriptors.astype(np.uint8).tobytes()
    except Exception as e:
        logger.warning("ORB feature extraction failed: %s", e)
        return None


def deserialize_orb_descriptors(raw_bytes: Optional[bytes]) -> Optional[np.ndarray]:
    """
    Safely reconstruct ORB descriptor matrix from raw bytes without pickle.
    Each ORB descriptor row has 32 columns of uint8.
    """
    if not raw_bytes or len(raw_bytes) == 0:
        return None
    try:
        arr = np.frombuffer(raw_bytes, dtype=np.uint8)
        if arr.size % 32 != 0:
            return None
        return arr.reshape(-1, 32)
    except Exception as e:
        logger.warning("Failed to deserialize ORB descriptors: %s", e)
        return None


class MatchVerdict:
    VERIFIED_MATCH = "VERIFIED_MATCH"
    UNCERTAIN = "UNCERTAIN"
    NO_MATCH = "NO_MATCH"


def match_query_against_candidates(
    query_pil: Image.Image,
    candidates: list,
    hamming_filter_max: int = 24,
) -> Tuple[str, float, Optional[object], dict]:
    """
    Two-Tier Computer Vision Matching Pipeline:
    - Stage 1 (Fast Filter): Compute query pHash & dHash; filter candidates via Hamming distance.
    - Stage 2 (Precision Verification): Verify top candidates with OpenCV ORB keypoint BFMatcher + Lowe's test.
    - Verdict:
        confidence >= 0.85 -> VERIFIED_MATCH
        0.65 <= confidence < 0.85 -> UNCERTAIN
        confidence < 0.65 -> NO_MATCH

    Returns:
        Tuple of (verdict, confidence_score, best_candidate, diagnostic_info)
    """
    if not candidates:
        return MatchVerdict.NO_MATCH, 0.0, None, {"reason": "No registered images in database"}

    # 1. Query Hash Extraction
    q_phash_str, q_dhash_str = extract_perceptual_hashes(query_pil)
    q_phash = imagehash.hex_to_hash(q_phash_str)
    q_dhash = imagehash.hex_to_hash(q_dhash_str)

    # 2. Stage 1: Fast Hamming Distance Filter
    filtered_candidates = []
    for cand in candidates:
        try:
            c_phash = imagehash.hex_to_hash(cand.phash)
            phash_dist = q_phash - c_phash
            if cand.dhash:
                c_dhash = imagehash.hex_to_hash(cand.dhash)
                dhash_dist = q_dhash - c_dhash
            else:
                dhash_dist = phash_dist

            if phash_dist <= hamming_filter_max or dhash_dist <= hamming_filter_max:
                filtered_candidates.append((cand, phash_dist, dhash_dist))
        except Exception as e:
            logger.warning("Hash comparison error for candidate %s: %s", getattr(cand, "id", "unknown"), e)
            continue

    if not filtered_candidates:
        return MatchVerdict.NO_MATCH, 0.15, None, {
            "stage": "filter",
            "reason": "No candidates passed perceptual hash threshold",
            "query_phash": q_phash_str
        }

    # Sort filtered candidates by lowest phash distance
    filtered_candidates.sort(key=lambda x: x[1])
    top_candidates = filtered_candidates[:8]  # inspect top 8

    # 3. Stage 2: Precision Verification with OpenCV ORB
    q_orb_bytes = extract_orb_descriptors(query_pil, max_features=500)
    q_des = deserialize_orb_descriptors(q_orb_bytes)

    best_cand = None
    best_confidence = 0.0
    best_diagnostics = {}

    bf = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=False)

    for cand, p_dist, d_dist in top_candidates:
        # Calculate perceptual hash similarity score (0.0 to 1.0)
        p_sim = max(0.0, 1.0 - (p_dist / 32.0))
        d_sim = max(0.0, 1.0 - (d_dist / 32.0))
        hash_score = 0.65 * p_sim + 0.35 * d_sim

        c_des = deserialize_orb_descriptors(cand.orb_descriptors)

        orb_good_matches = 0
        orb_score = 0.0

        if q_des is not None and c_des is not None and len(q_des) >= 2 and len(c_des) >= 2:
            try:
                raw_matches = bf.knnMatch(c_des, q_des, k=2)
                for m_n in raw_matches:
                    if len(m_n) == 2:
                        m, n = m_n
                        if m.distance < 0.75 * n.distance:
                            orb_good_matches += 1

                min_pts = min(len(c_des), len(q_des))
                ratio = orb_good_matches / max(min_pts, 1)
                # 20+ good keypoints is a strong match indicator
                orb_score = min(1.0, (orb_good_matches / 20.0) * 0.7 + (ratio * 2.0) * 0.3)
            except Exception as e:
                logger.warning("KNN match failed: %s", e)

        # Calibrate overall confidence
        if p_dist == 0:
            # Identical perceptual hash
            cand_conf = 0.95 + 0.05 * orb_score
        elif p_dist <= 4:
            # Very close hash (slight resize/compression)
            if c_des is not None and q_des is not None:
                cand_conf = 0.50 * hash_score + 0.50 * orb_score
                # Boost if p_dist <= 2
                if p_dist <= 2 and cand_conf >= 0.80:
                    cand_conf = min(1.0, cand_conf + 0.10)
            else:
                cand_conf = hash_score
        elif p_dist <= 10:
            if orb_good_matches >= 15:
                # ORB confirms match despite hash shift
                cand_conf = 0.35 * hash_score + 0.65 * orb_score
            else:
                cand_conf = 0.60 * hash_score + 0.40 * orb_score
        else:
            # Higher distance
            if orb_good_matches >= 25:
                cand_conf = 0.30 * hash_score + 0.70 * orb_score
            else:
                cand_conf = min(0.60, hash_score * 0.7)

        cand_conf = round(float(np.clip(cand_conf, 0.0, 1.0)), 2)

        if cand_conf > best_confidence:
            best_confidence = cand_conf
            best_cand = cand
            best_diagnostics = {
                "phash_distance": int(p_dist),
                "dhash_distance": int(d_dist),
                "orb_good_matches": int(orb_good_matches),
                "hash_score": float(round(hash_score, 2)),
                "orb_score": float(round(orb_score, 2)),
                "public_image_uid": str(cand.public_image_uid),
            }

    # Determine final verdict
    if best_confidence >= 0.85:
        verdict = MatchVerdict.VERIFIED_MATCH
    elif best_confidence >= 0.65:
        verdict = MatchVerdict.UNCERTAIN
    else:
        verdict = MatchVerdict.NO_MATCH

    return verdict, best_confidence, best_cand, best_diagnostics
