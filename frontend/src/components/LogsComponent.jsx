import { useState } from 'react';
import { getLogs } from '../services/apiService';

const LogsComponent = () => {
  const [logs, setLogs] = useState([]);
  const [filters, setFilters] = useState({
    startDate: '',
    endDate: '',
    itemId: '',
    userId: '',
    actionType: ''
  });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const fetchLogs = async () => {
    setLoading(true);
    setError(null);
    
    try {
      const queryParams = new URLSearchParams(
        Object.entries(filters).filter(([_, v]) => v) // Remove empty filters
      ).toString();
      
      const response = await getLogs(queryParams);
      setLogs(response.data.logs);
    } catch (err) {
      console.error('Error fetching logs:', err);
      setError('Failed to load logs.');
    }

    setLoading(false);
  };

  return (
    <div>
      <div className="flex-1 flex flex-col items-center justify-start p-10 space-y-6">
        <h1 className="text-3xl font-bold">Logs</h1>

        <div className="bg-white p-4 shadow-md rounded-md w-full max-w-3xl">
          <h2 className="text-lg font-semibold mb-2">Filter Logs</h2>
          <div className="grid grid-cols-2 gap-4">
            <input
              type="datetime-local"
              value={filters.startDate}
              onChange={(e) => setFilters({ ...filters, startDate: e.target.value })}
              className="border p-2 rounded"
              placeholder="Start Date"
            />
            <input
              type="datetime-local"
              value={filters.endDate}
              onChange={(e) => setFilters({ ...filters, endDate: e.target.value })}
              className="border p-2 rounded"
              placeholder="End Date"
            />
            <input
              type="text"
              value={filters.itemId}
              onChange={(e) => setFilters({ ...filters, itemId: e.target.value })}
              className="border p-2 rounded"
              placeholder="Item ID"
            />
            <input
              type="text"
              value={filters.userId}
              onChange={(e) => setFilters({ ...filters, userId: e.target.value })}
              className="border p-2 rounded"
              placeholder="User ID"
            />
            <select
              value={filters.actionType}
              onChange={(e) => setFilters({ ...filters, actionType: e.target.value })}
              className="border p-2 rounded"
            >
              <option value="">Select Action Type</option>
              <option value="placement">Placement</option>
              <option value="retrieval">Retrieval</option>
              <option value="rearrangement">Rearrangement</option>
              <option value="disposal">Disposal</option>
            </select>
          </div>
          <button
            onClick={fetchLogs}
            className="bg-blue-500 text-white px-4 py-2 mt-4 w-full rounded"
          >
            🔍 Get Logs
          </button>
        </div>

        <div className="bg-white p-4 shadow-md rounded-md w-full max-w-4xl">
          <h2 className="text-lg font-semibold">Logs</h2>
          {loading ? (
            <p>Loading logs...</p>
          ) : error ? (
            <p className="text-red-500">{error}</p>
          ) : logs.length > 0 ? (
            <table className="w-full border-collapse border">
              <thead>
                <tr className="bg-gray-200">
                  <th className="border p-2">Timestamp</th>
                  <th className="border p-2">User ID</th>
                  <th className="border p-2">Action</th>
                  <th className="border p-2">Item ID</th>
                  <th className="border p-2">Details</th>
                </tr>
              </thead>
              <tbody>
                {logs.map((log, index) => (
                  <tr key={index} className="border">
                    <td className="border p-2">{log.timestamp}</td>
                    <td className="border p-2">{log.userId}</td>
                    <td className="border p-2">{log.actionType}</td>
                    <td className="border p-2">{log.itemId}</td>
                    <td className="border p-2">
                      {log.details ? (
                        <>
                          {log.details.fromContainer && <div>From: {log.details.fromContainer}</div>}
                          {log.details.toContainer && <div>To: {log.details.toContainer}</div>}
                          {log.details.reason && <div>Reason: {log.details.reason}</div>}
                        </>
                      ) : (
                        'No details'
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <p>No logs found.</p>
          )}
        </div>
      </div>
    </div>
  );
};

export default LogsComponent;
