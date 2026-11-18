import json
import math
import sys

import cv2


def main(path):
    # El seguimiento procesa pocos fotogramas en una instancia de 512 MB.
    # Un solo hilo evita pools paralelos innecesarios y reduce picos de CPU.
    cv2.setNumThreads(1)
    cascade_path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
    detector = cv2.CascadeClassifier(cascade_path)
    if detector.empty():
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
    step = max(1, int(math.ceil(duration / 30.0)))
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
        gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
        faces = detector.detectMultiScale(
            gray, scaleFactor=1.1, minNeighbors=5, minSize=(18, 18)
        )
        if len(faces) == 0:
            continue
        choices = []
        for x, y, face_w, face_h in faces:
            center_x = (float(x) + float(face_w) / 2.0) / scale
            area = float(face_w * face_h)
            choices.append((center_x, area, float(face_w) / 320.0))
        if previous_x is None:
            chosen_x, _, chosen_size = max(choices, key=lambda item: item[1])
        else:
            nearest_x, nearest_area, nearest_size = min(choices, key=lambda item: abs(item[0] - previous_x))
            if abs(nearest_x - previous_x) <= width * 0.30:
                chosen_x, chosen_size = nearest_x, nearest_size
            else:
                chosen_x, _, chosen_size = max(choices, key=lambda item: item[1])
        previous_x = chosen_x
        centers.append({"t": float(second), "x": float(chosen_x), "size": chosen_size})
    cap.release()
    if len(centers) < max(3, int(len(sample_times) * 0.12)):
        return
    print(json.dumps({"width": width, "height": height, "centers": centers}))


if __name__ == "__main__" and len(sys.argv) > 1:
    try:
        main(sys.argv[1])
    except Exception:
        pass
