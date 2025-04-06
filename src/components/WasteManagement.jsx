import { useState } from 'react';
import { identifyWaste, returnWastePlan, completeUndocking } from '../services/apiService';

const WasteManagement = () => {
  const [wasteItems, setWasteItems] = useState([]);
  const [returnPlan, setReturnPlan] = useState(null);
  const [undockingInfo, setUndockingInfo] = useState({
    undockingContainerId: '',
    undockingDate: '',
    maxWeight: '',
  });
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState('');

  const fetchWasteItems = async () => {
    setLoading(true);
    setMessage('');
    try {
      const response = await identifyWaste();
      setWasteItems(response.data.wasteItems);
    } catch (error) {
      setMessage(' Error fetching waste items.');
      console.error(error);
    }
    setLoading(false);
  };

  const handleReturnPlan = async (e) => {
    e.preventDefault();
    setLoading(true);
    setMessage('');
    try {
      const response = await returnWastePlan({
        ...undockingInfo,
        undockingDate: new Date(undockingInfo.undockingDate).toISOString(),
        maxWeight: parseFloat(undockingInfo.maxWeight),
      });
      setReturnPlan(response.data);
    } catch (error) {
      setMessage(' Error requesting return plan.');
      console.error(error);
    }
    setLoading(false);
  };

  const handleCompleteUndocking = async () => {
    setLoading(true);
    setMessage('');
    try {
      const response = await completeUndocking({
        undockingContainerId: undockingInfo.undockingContainerId,
        timestamp: new Date().toISOString(),
      });
      if (response.data.success) {
        setMessage(' Undocking completed successfully!');
      } else {
        setMessage(' Failed to complete undocking.');
      }
    } catch (error) {
      setMessage(' Error completing undocking.');
      console.error(error);
    }
    setLoading(false);
  };

  return (
    <div className="flex">
      <div className="flex-1 p-6 bg-white shadow-lg rounded-lg max-w-4xl mx-auto">
        <h2 className="text-2xl font-semibold mb-4"> Waste Management</h2>
        
        <button onClick={fetchWasteItems} className="w-full py-2 bg-blue-500 text-white rounded-md hover:bg-blue-700">
          Identify Waste Items
        </button>
        {loading && <p className="mt-2 text-gray-500">Loading...</p>}
        {message && <p className="mt-2 text-red-500">{message}</p>}

        {wasteItems.length > 0 && (
          <div className="mt-4 p-4 bg-gray-100 rounded-lg">
            <h3 className="text-lg font-medium">Waste Items:</h3>
            <ul>
              {wasteItems.map((item) => (
                <li key={item.itemId} className="p-2 border-b">
                  <strong>{item.name}</strong> - {item.reason}
                </li>
              ))}
            </ul>
          </div>
        )}

        <form onSubmit={handleReturnPlan} className="mt-6 space-y-4">
          <h3 className="text-lg font-medium">Request Return Plan</h3>
          <input type="text" placeholder="Undocking Container ID" name="undockingContainerId" value={undockingInfo.undockingContainerId} onChange={(e) => setUndockingInfo({ ...undockingInfo, undockingContainerId: e.target.value })} required className="w-full border p-2 rounded-md" />
          <input type="date" name="undockingDate" value={undockingInfo.undockingDate} onChange={(e) => setUndockingInfo({ ...undockingInfo, undockingDate: e.target.value })} required className="w-full border p-2 rounded-md" />
          <input type="number" placeholder="Max Weight (kg)" name="maxWeight" value={undockingInfo.maxWeight} onChange={(e) => setUndockingInfo({ ...undockingInfo, maxWeight: e.target.value })} required className="w-full border p-2 rounded-md" />
          <button type="submit" className="w-full py-2 bg-green-500 text-white rounded-md hover:bg-green-700">Get Return Plan</button>
        </form>
        
        {returnPlan && (
          <div className="mt-4 p-4 bg-gray-100 rounded-lg">
            <h3 className="text-lg font-medium">Return Plan:</h3>
            <pre className="text-sm whitespace-pre-wrap">{JSON.stringify(returnPlan, null, 2)}</pre>
          </div>
        )}
        
        <button onClick={handleCompleteUndocking} className="mt-6 w-full py-2 bg-red-500 text-white rounded-md hover:bg-red-700">
          Complete Undocking
        </button>
      </div>
    </div>
  );
};

export default WasteManagement;
