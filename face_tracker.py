import json
import math
import sys

import cv2


def main(path):
    # Detección ligera a baja resolución para no cargar el servidor.
    cv2.setNumThreads(1)
    base = cv2.data.haarcascades
    frontal = cv2.CascadeClassifier(base + "haarcascade_frontalface_default.xml")
    profile = cv2.CascadeClassifier(base + "haarcascade_profileface.xml")
    upper = cv2.CascadeClassifier(base + "haarcascade_upperbody.xml")
    if frontal.empty():
        return
    cap = cv2.VideoCapture(path)
    if not cap.isOpened():
        return
    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    frame_count = cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
    duration = frame_count / fps if fps > 0 else 0
    if width < 2 or height < 2 or duration < 3:
        cap.release()
        return

    # Hasta 60 muestras por clip; detección sobre una imagen de 320 px.
    step = max(1, int(math.ceil(duration / 60.0)))
    sample_times = list(range(0, max(1, int(duration)), step))
    centers = []
    previous_x = None
    scale = 320.0 / width
    resized_height = max(1, int(height * scale))

    for second in sample_times:
        cap.set(cv2.CAP_PROP_POS_MSEC, second * 1000.0)
        ok, frame = cap.read()
        if not ok:
            continue
        small = cv2.resize(frame, (320, resized_height), interpolation=cv2.INTER_AREA)
        gray = cv2.equalizeHist(cv2.cvtColor(small, cv2.COLOR_BGR2GRAY))

        # Frontal + perfil: ayuda a reconocer grupos aunque alguien esté de lado.
        face_boxes = list(frontal.detectMultiScale(
            gray, scaleFactor=1.08, minNeighbors=4, minSize=(12, 12)
        ))
        if not profile.empty():
            profile_boxes = list(profile.detectMultiScale(
                gray, scaleFactor=1.08, minNeighbors=3, minSize=(12, 12)
            ))
            for candidate in profile_boxes:
                x, y, w, h = [int(v) for v in candidate]
                duplicate = False
                for fx, fy, fw, fh in face_boxes:
                    ix1, iy1 = max(x, fx), max(y, fy)
                    ix2, iy2 = min(x + w, fx + fw), min(y + h, fy + fh)
                    intersection = max(0, ix2 - ix1) * max(0, iy2 - iy1)
                    union = w * h + fw * fh - intersection
                    if union and intersection / union > 0.30:
                        duplicate = True
                        break
                if not duplicate:
                    face_boxes.append((x, y, w, h))

        choices = []
        for x, y, face_w, face_h in face_boxes:
            center_x = (float(x) + float(face_w) / 2.0) / scale
            choices.append((center_x, float(face_w * face_h), float(face_w) / 320.0))

        # Si el detector de torso encuentra varias personas, preservar el plano completo.
        body_count = 0
        if not upper.empty():
            bodies = upper.detectMultiScale(
                gray, scaleFactor=1.08, minNeighbors=3, minSize=(24, 32)
            )
            body_count = len(bodies)

        if len(choices) >= 2 or body_count >= 2:
            centers.append({
                "t": float(second), "x": float(width / 2.0),
                "size": 0.0, "face_count": max(len(choices), body_count, 2)
            })
            continue

        if not choices:
            # Guardar también las muestras sin rostro: no asumir que el único
            # rostro detectado representa toda la escena.
            centers.append({
                "t": float(second), "x": float(width / 2.0),
                "size": 0.0, "face_count": 0
            })
            continue

        nearest_x, _, nearest_size = choices[0]
        if previous_x is None:
            chosen_x = nearest_x
        elif abs(nearest_x - previous_x) <= width * 0.22:
            chosen_x = nearest_x
        else:
            chosen_x = previous_x
        previous_x = chosen_x
        centers.append({
            "t": float(second), "x": float(chosen_x),
            "size": nearest_size, "face_count": 1
        })

    cap.release()
    if len(centers) < max(3, int(len(sample_times) * 0.12)):
        return
    print(json.dumps({"width": width, "height": height, "centers": centers}))


if __name__ == "__main__" and len(sys.argv) > 1:
    try:
        main(sys.argv[1])
    except Exception:
        pass
