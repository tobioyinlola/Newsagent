import { PutObjectCommand, S3Client } from "@aws-sdk/client-s3";
import fs from "node:fs";
import path from "node:path";

// S3-compatible (R2 / MinIO) when STORAGE_ENDPOINT is set, otherwise a local directory for dev and tests.
export async function putFile(key: string, file: string): Promise<void> {
  if (process.env.STORAGE_ENDPOINT) {
    const s3 = new S3Client({
      endpoint: process.env.STORAGE_ENDPOINT, region: "auto", forcePathStyle: true,
      credentials: { accessKeyId: process.env.STORAGE_ACCESS_KEY!, secretAccessKey: process.env.STORAGE_SECRET_KEY! },
    });
    await s3.send(new PutObjectCommand({ Bucket: process.env.STORAGE_BUCKET!, Key: key, Body: fs.createReadStream(file), ContentType: file.endsWith(".png") ? "image/png" : "video/mp4" }));
  } else {
    const dest = path.join(process.env.LOCAL_OUTPUT_DIR || "out/uploads", key);
    fs.mkdirSync(path.dirname(dest), { recursive: true });
    fs.copyFileSync(file, dest);
  }
}
