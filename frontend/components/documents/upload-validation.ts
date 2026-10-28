// Mirrors backend/app/services/document_service.py and core/config.py.
// The backend does not expose upload capabilities through an API. Keep these in
// sync with the deployment's MAX_UPLOAD_SIZE_MB when its default changes.
export const MAX_UPLOAD_BYTES = 50 * 1024 * 1024;
export const UPLOAD_EXTENSIONS = ["pdf", "doc", "docx", "txt", "pptx", "jpg", "jpeg", "png"];

const SIGNATURES: Record<string, number[]> = {
  pdf: [0x25, 0x50, 0x44, 0x46, 0x2d],
  doc: [0xd0, 0xcf, 0x11, 0xe0, 0xa1, 0xb1, 0x1a, 0xe1],
  docx: [0x50, 0x4b, 0x03, 0x04], pptx: [0x50, 0x4b, 0x03, 0x04],
  jpg: [0xff, 0xd8, 0xff], jpeg: [0xff, 0xd8, 0xff],
  png: [0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a],
};

export async function validateUploadFile(file: File): Promise<string | null> {
  const extension = file.name.includes(".") ? file.name.split(".").pop()!.toLowerCase() : "";
  if (!UPLOAD_EXTENSIONS.includes(extension)) return "Định dạng không được hỗ trợ. Chọn PDF, DOC, DOCX, TXT, PPTX, JPG, JPEG hoặc PNG.";
  if (file.size > MAX_UPLOAD_BYTES) return "Tệp vượt quá giới hạn 50 MiB (52.428.800 byte).";
  const header = new Uint8Array(await file.slice(0, 16).arrayBuffer());
  const valid = extension === "txt" ? !header.includes(0) : SIGNATURES[extension].every((byte, index) => header[index] === byte);
  return valid ? null : "Nội dung tệp không khớp với định dạng. Hãy chọn tệp gốc, không chỉ đổi đuôi tệp.";
}

// Storage constraints: Document.title String(500), Tag.name String(100).
export function validateUploadMetadata(title: string, filename: string, tags: string) {
  return {
    title: [...(title.trim() || filename)].length > 500 ? "Tiêu đề tối đa 500 ký tự. Hãy nhập tiêu đề ngắn hơn." : null,
    tags: tags.split(",").some((tag) => [...tag.trim()].length > 100) ? "Mỗi thẻ tối đa 100 ký tự." : null,
  };
}
