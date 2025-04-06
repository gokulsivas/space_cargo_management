import { useState } from 'react';
import SideNavBar from "../components/dashboard/sideNavBar";
import { retrieveItem } from '../services/apiService';

const RetrieveItemComponent = () => {
  const [itemId, setItemId] = useState('');
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState('');

  const handleRetrieve = async (e) => {
    e.preventDefault();
    setLoading(true);
    setMessage('');

    try {
      const response = await retrieveItem(itemId);
      if (response.data.success) {
        setMessage(`Item retrieved successfully!`);
      } else {
        setMessage('Failed to retrieve item.');
      }
    } catch (error) {
      console.error('Error retrieving item:', error);
      setMessage('Error occurred while retrieving item.');
    }

    setLoading(false);
  };

  return (
    <div className="flex h-screen">
      <div className="hidden md:block md:w-64 bg-white shadow-lg fixed h-full">
        <SideNavBar />
      </div>

      <div className="flex-1 flex justify-center items-center p-8 ml-64">
        <div className="max-w-lg w-full bg-white shadow-md rounded-lg p-6">
          <h2 className="text-2xl font-semibold mb-4 text-center">Retrieve an Item</h2>
          <form onSubmit={handleRetrieve} className="space-y-4">
            <input 
              type="text" 
              value={itemId} 
              onChange={(e) => setItemId(e.target.value)} 
              placeholder="Item ID" 
              required 
              className="w-full border p-2 rounded-md"
            />
            <button 
              type="submit"
              className={`w-full py-2 text-white rounded-md ${loading ? 'bg-gray-400' : 'bg-blue-500 hover:bg-blue-600'}`}
              disabled={loading}
            >
              {loading ? 'Retrieving Item...' : 'Retrieve Item'}
            </button>
          </form>
          {message && (
            <p className={`mt-4 text-center font-medium ${message.includes('✅') ? 'text-green-600' : 'text-red-600'}`}>
              {message}
            </p>
          )}
        </div>
      </div>
    </div>
  );
};

export default RetrieveItemComponent;
