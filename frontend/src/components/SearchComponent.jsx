import { useState } from 'react';
import { searchItem, retrieveItem } from '../services/apiService';

const SearchComponent = () => {
  const [itemId, setItemId] = useState('');
  const [itemDetails, setItemDetails] = useState(null);
  const [retrievalSteps, setRetrievalSteps] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const handleSearch = async () => {
    setLoading(true);
    setError('');
    try {
      const response = await searchItem({ itemId });
      if (response.data.found) {
        setItemDetails(response.data.item);
        setRetrievalSteps(response.data.retrievalSteps || []);
      } else {
        setItemDetails(null);
        setError('Item not found');
      }
    } catch (error) {
      console.error('Error searching item:', error);
      setError('Failed to fetch item details');
    }
    setLoading(false);
  };

  const handleRetrieve = async () => {
    try {
      await retrieveItem({ itemId, userId: 'user123', timestamp: new Date().toISOString() });
      alert('Item retrieved successfully!');
    } catch (error) {
      console.error('Error retrieving item:', error);
      alert('Failed to retrieve item');
    }
  };

  return (
    <div className="p-6 bg-gray-100 shadow-md rounded-md w-96">
      <h2 className="text-xl font-bold mb-4">Search Item</h2>
      
      <input
        type="text"
        value={itemId}
        onChange={(e) => setItemId(e.target.value)}
        placeholder="Enter Item ID"
        className="border p-2 w-full mb-2 rounded-md"
      />

      <button 
        onClick={handleSearch} 
        className="bg-blue-500 text-white py-2 px-4 rounded-md w-full mb-2"
      >
        {loading ? 'Searching...' : 'Search'}
      </button>

      {error && <p className="text-red-500 text-sm">{error}</p>}

      {itemDetails && (
        <div className="mt-4 p-4 bg-white rounded-md shadow">
          <h3 className="text-lg font-semibold mb-2">Item Details</h3>
          <p><strong>Name:</strong> {itemDetails.name}</p>
          <p><strong>Container:</strong> {itemDetails.containerId}</p>
          <p><strong>Zone:</strong> {itemDetails.zone}</p>
          
          <div className="mt-2 p-2 bg-gray-100 rounded-md">
            <h4 className="text-sm font-semibold">Position:</h4>
            <p><strong>Start:</strong> W: {itemDetails.position.startCoordinates.width}, D: {itemDetails.position.startCoordinates.depth}, H: {itemDetails.position.startCoordinates.height}</p>
            <p><strong>End:</strong> W: {itemDetails.position.endCoordinates.width}, D: {itemDetails.position.endCoordinates.depth}, H: {itemDetails.position.endCoordinates.height}</p>
          </div>

          <button 
            onClick={handleRetrieve} 
            className="bg-green-500 text-white py-2 px-4 mt-4 rounded-md w-full"
          >
            Retrieve Item
          </button>

          {retrievalSteps.length > 0 && (
            <div className="mt-4 p-2 bg-gray-100 rounded-md">
              <h4 className="text-sm font-semibold mb-1">Retrieval Steps:</h4>
              <ul className="list-disc list-inside text-sm">
                {retrievalSteps.map((step, index) => (
                  <li key={index}>
                    Step {step.step}: {step.action} <strong>{step.itemName}</strong>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </div>
  );
};

export default SearchComponent;
