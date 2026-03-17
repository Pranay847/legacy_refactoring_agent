import React, { useState } from 'react';
import { useDropzone } from 'react-dropzone';

function FolderUploader() {
  const [files, SetFiles] = useState([]);

  const onDrop = (acceptedFiles) => {
    SetFiles(acceptedFiles);
  }

  const { getRootProps, getInputProps } = useDropzone({
    onDrop,
    noClick: false
  });

  const uploadFiles = async () => {
    const formData = new FormData();

    files.forEach((file) => {
      formData.append("files", file);
    });

    await fetch("http://localhost:8000/api/ingest/", {
      method: "POST",
      body: formData
    });
  };

  return (
    <div>
    
      <div
      {...getRootProps()}
      style={{
        border: '2px dashed gray',
        padding: '40px',
        marginBottom: '20px',
        cursor: 'pointer'
      }}
      >
        <input {...getInputProps()} webkitdirectory="true" multiple />
        <p>Drag & drop a folder here</p>
      </div>
      <p>{files.length} files selected</p>
      <button ocClick={uploadFiles}>Upload</button>

    </div>
  )
}

export default FolderUploader