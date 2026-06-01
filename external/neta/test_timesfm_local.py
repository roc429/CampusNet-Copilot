# -*- coding: utf-8 -*-
import numpy as np
import timesfm


MODEL_PATH = "/home/jowin/Desktop/neta/models/timesfm-2.5-200m-pytorch"


def main():
    print("Loading TimesFM local model...")
    print("Model path:", MODEL_PATH)

    model = timesfm.TimesFm(
        hparams=timesfm.TimesFmHparams(
            backend="torch",
            per_core_batch_size=32,
            horizon_len=24,
            input_patch_len=32,
            output_patch_len=128,
            num_layers=50,
            model_dims=1280,
            use_positional_embedding=False,
        ),
        checkpoint=timesfm.TimesFmCheckpoint(
            path=MODEL_PATH
        ),
    )

    print("MODEL OK")

    # 构造一段假的 AP 负载序列
    context = np.array([
        0.10, 0.12, 0.11, 0.13, 0.15, 0.18, 0.20, 0.22,
        0.25, 0.28, 0.30, 0.33, 0.35, 0.37, 0.40, 0.42,
        0.45, 0.48, 0.50, 0.52, 0.55, 0.57, 0.60, 0.62,
        0.64, 0.66, 0.68, 0.70, 0.72, 0.74, 0.75, 0.76
    ], dtype=np.float32)

    print("Running forecast...")

    point_forecast, quantile_forecast = model.forecast(
        [context],
        freq=[0]
    )

    point = np.asarray(point_forecast)[0]
    quantile = np.asarray(quantile_forecast)[0]

    print("Forecast shape:", point.shape)
    print("Quantile shape:", quantile.shape)

    print("\nFuture 1-24 forecast:")
    for i in range(min(24, len(point))):
        if quantile.ndim == 2 and quantile.shape[1] >= 10:
            q10 = quantile[i, 1]
            q50 = quantile[i, 5]
            q90 = quantile[i, 9]
        elif quantile.ndim == 2 and quantile.shape[1] >= 3:
            q10 = quantile[i, 0]
            q50 = quantile[i, quantile.shape[1] // 2]
            q90 = quantile[i, -1]
        else:
            q10 = point[i]
            q50 = point[i]
            q90 = point[i]

        print(
            "Hour {:02d}: point={:.6f}, q10={:.6f}, q50={:.6f}, q90={:.6f}".format(
                i + 1,
                float(point[i]),
                float(q10),
                float(q50),
                float(q90)
            )
        )


if __name__ == "__main__":
    main()