import { useDropzone } from "react-dropzone";
import { UploadCloud } from "lucide-react";
import { uploadSessionFiles } from "../api";

export default function UploadPanel({ session, setSessionFiles, setSessionResults, setSessionStatus }) {
  const onDrop = async (acceptedFiles) => {
    if (!session) return;

    setSessionFiles(session.id, acceptedFiles);
    setSessionStatus(session.id, "uploading");

    try {
      const data = await uploadSessionFiles(session.id, acceptedFiles);
      setSessionResults(session.id, data.files || []);
      setSessionStatus(session.id, "ingested");
    } catch (error) {
      console.error(error);
      setSessionStatus(session.id, "error");
    }
  };

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    noClick: false,
    multiple: true,
  });

  return (
    <div className="rounded-2xl border border-zinc-200 bg-white dark:bg-zinc-900 p-5 shadow-sm">
      <div
        {...getRootProps()}
        className={`cursor-pointer rounded-2xl border-2 border-dashed p-8 text-center transition ${
          isDragActive
            ? "border-blue-500 bg-blue-50"
            : "border-zinc-300 bg-zinc-50 dark:bg-zinc-800 hover:border-zinc-400"
        }`}
      >
        <input {...getInputProps()} webkitdirectory="true" directory="" multiple />
        <div className="mx-auto flex max-w-md flex-col items-center">
          <UploadCloud className="mb-4 text-zinc-500" size={36} />
          <h3 className="text-lg font-semibold text-zinc-900 dark:text-zinc-300">
            Drag and drop a project folder
          </h3>
          <p className="mt-2 text-sm text-zinc-500">
            Upload source code repositories or documentation folders for local LLM ingestion.
          </p>
        </div>
      </div>

      {session && session.files.length > 0 && (
        <div className="mt-4">
          <p className="mb-2 text-sm font-medium text-zinc-700">Selected files</p>
          <div className="max-h-40 overflow-y-auto rounded-xl border border-zinc-200 bg-zinc-50 dark:bg-zinc-800 p-3">
            <ul className="space-y-1 text-sm text-zinc-600">
              {session.files.slice(0, 10).map((file, index) => (
                <li key={`${file.name}-${index}`} className="truncate">
                  {file.webkitRelativePath || file.name}
                </li>
              ))}
            </ul>
            {session.files.length > 10 && (
              <p className="mt-2 text-xs text-zinc-500">
                + {session.files.length - 10} more files
              </p>
            )}
          </div>
        </div>
      )}
    </div>
  );
}