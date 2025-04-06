import { useState } from 'react';
import { importItems, importContainers, exportArrangement } from '../services/apiService';

const ImportExport = () => {
  const [itemsFile, setItemsFile] = useState(null);
  const [containersFile, setContainersFile] = useState(null);
  const [importResult, setImportResult] = useState(null);
  const [exporting, setExporting] = useState(false);

  // Modified: Now passing the file directly to the API service function.
  const handleFileUpload = async (file, importFunction, type) => {
    if (!file) return alert(`Please select a ${type} file!`);
    try {
      const response = await importFunction(file);
      setImportResult({ type, data: response.data });
    } catch (error) {
      console.error(`Import ${type} Error:`, error);
    }
  };

  const handleExport = async () => {
    setExporting(true);
    try {
      const response = await exportArrangement();
      const blob = new Blob([response.data], { type: 'text/csv' });
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = 'arrangement.csv';
      a.click();
      window.URL.revokeObjectURL(url);
    } catch (error) {
      console.error('Export Error:', error);
    }
    setExporting(false);
  };

  return (
      <div className="bg-white shadow-lg rounded-lg p-6 w-full max-w-3xl mx-auto">
        <h2 className="text-2xl font-bold text-gray-800 mb-4">Import / Export Data</h2>

        <div className="mb-4">
          <label className="block text-gray-600 font-semibold">Import Items (CSV)</label>
          <input type="file" accept=".csv" onChange={(e) => setItemsFile(e.target.files[0])} className="w-full border p-2 rounded" />
          <button onClick={() => handleFileUpload(itemsFile, importItems, 'Items')} className="bg-blue-500 text-white px-4 py-2 mt-2 rounded w-full">
            Upload Items
          </button>
        </div>

        <div className="mb-4">
          <label className="block text-gray-600 font-semibold">Import Containers (CSV)</label>
          <input type="file" accept=".csv" onChange={(e) => setContainersFile(e.target.files[0])} className="w-full border p-2 rounded" />
          <button onClick={() => handleFileUpload(containersFile, importContainers, 'Containers')} className="bg-green-500 text-white px-4 py-2 mt-2 rounded w-full">
            Upload Containers
          </button>
        </div>

        <div className="mb-4">
          <button onClick={handleExport} className="bg-purple-500 text-white px-4 py-2 rounded w-full" disabled={exporting}>
            {exporting ? 'Exporting...' : 'Export Arrangement'}
          </button>
        </div>

        {importResult && (
            <div className="mt-4 bg-gray-100 p-4 rounded">
              <h3 className="text-lg font-semibold">{importResult.type} Import Results</h3>
              <pre className="text-sm text-gray-700 overflow-auto">{JSON.stringify(importResult.data, null, 2)}</pre>
            </div>
        )}
      </div>
  );
};

export default ImportExport;
