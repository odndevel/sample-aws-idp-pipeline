import { createFileRoute } from '@tanstack/react-router';
import { CSSProperties, useState } from 'react';
import { useAwsClient } from '../hooks/useAwsClient';

export const Route = createFileRoute('/test')({
  component: RouteComponent,
});

const buttonStyle: CSSProperties = {
  padding: '8px 16px',
  backgroundColor: '#007bff',
  color: 'white',
  border: 'none',
  borderRadius: '4px',
  cursor: 'pointer',
};

const deleteButtonStyle: CSSProperties = {
  ...buttonStyle,
  backgroundColor: '#dc3545',
};

const disabledButtonStyle: CSSProperties = {
  ...buttonStyle,
  backgroundColor: '#6c757d',
  cursor: 'not-allowed',
};

function RouteComponent() {
  const { fetchApi, uploadToS3 } = useAwsClient();
  const [tables, setTables] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);
  const [newTableName, setNewTableName] = useState('');
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);
  const [uploadResult, setUploadResult] = useState<string>('');

  const handleGetTables = async () => {
    setLoading(true);
    const data = await fetchApi<string[]>('tables');
    setTables(data);
    setLoading(false);
  };

  const handleCreateTable = async () => {
    if (!newTableName.trim()) return;
    await fetchApi<string>('tables', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name: newTableName }),
    });
    setNewTableName('');
    await handleGetTables();
  };

  const handleDeleteTable = async (name: string) => {
    await fetchApi<string>(`tables/${name}`, { method: 'DELETE' });
    await handleGetTables();
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    setSelectedFile(file ?? null);
    setUploadResult('');
  };

  const handleUpload = async () => {
    if (!selectedFile) return;
    setUploading(true);
    setUploadResult('');
    const key = `uploads/${Date.now()}_${selectedFile.name}`;
    await uploadToS3(selectedFile, key);
    setUploadResult(`Uploaded: ${key}`);
    setSelectedFile(null);
    setUploading(false);
  };

  return (
    <div style={{ padding: '20px' }}>
      <h1>API Test</h1>

      <section style={{ marginBottom: '20px' }}>
        <h2>Tables</h2>
        <div style={{ marginBottom: '10px' }}>
          <button
            onClick={handleGetTables}
            disabled={loading}
            style={loading ? disabledButtonStyle : buttonStyle}
          >
            {loading ? 'Loading...' : 'Load Tables'}
          </button>
        </div>
        <div style={{ marginBottom: '10px' }}>
          <input
            type="text"
            value={newTableName}
            onChange={(e) => setNewTableName(e.target.value)}
            placeholder="New table name"
            style={{
              padding: '8px',
              marginRight: '8px',
              borderRadius: '4px',
              border: '1px solid #ccc',
            }}
          />
          <button
            onClick={handleCreateTable}
            disabled={!newTableName.trim()}
            style={!newTableName.trim() ? disabledButtonStyle : buttonStyle}
          >
            Create Table
          </button>
        </div>
        <table
          style={{
            marginTop: '10px',
            borderCollapse: 'collapse',
            width: '100%',
          }}
        >
          <thead>
            <tr>
              <th
                style={{
                  border: '1px solid #ccc',
                  padding: '8px',
                  textAlign: 'left',
                }}
              >
                Table Name
              </th>
              <th
                style={{
                  border: '1px solid #ccc',
                  padding: '8px',
                  textAlign: 'left',
                  width: '100px',
                }}
              >
                Actions
              </th>
            </tr>
          </thead>
          <tbody>
            {tables.length === 0 ? (
              <tr>
                <td
                  colSpan={2}
                  style={{ border: '1px solid #ccc', padding: '8px' }}
                >
                  No tables loaded
                </td>
              </tr>
            ) : (
              tables.map((table) => (
                <tr key={table}>
                  <td style={{ border: '1px solid #ccc', padding: '8px' }}>
                    {table}
                  </td>
                  <td style={{ border: '1px solid #ccc', padding: '8px' }}>
                    <button
                      onClick={() => handleDeleteTable(table)}
                      style={deleteButtonStyle}
                    >
                      Delete
                    </button>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </section>

      <section style={{ marginBottom: '20px' }}>
        <h2>S3 Upload</h2>
        <div style={{ marginBottom: '10px' }}>
          <input
            type="file"
            onChange={handleFileChange}
            style={{ marginRight: '8px' }}
          />
          <button
            onClick={handleUpload}
            disabled={!selectedFile || uploading}
            style={
              !selectedFile || uploading ? disabledButtonStyle : buttonStyle
            }
          >
            {uploading ? 'Uploading...' : 'Upload'}
          </button>
        </div>
        {uploadResult && <div style={{ color: 'green' }}>{uploadResult}</div>}
      </section>
    </div>
  );
}
