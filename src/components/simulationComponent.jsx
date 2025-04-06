import { useState } from "react";
import { simulateDays } from "../services/apiService";

const TimeSimulation = () => {
  const [numOfDays, setNumOfDays] = useState("");
  const [toTimestamp, setToTimestamp] = useState("");
  const [itemsToBeUsed, setItemsToBeUsed] = useState([]);
  const [itemId, setItemId] = useState("");
  const [itemName, setItemName] = useState("");
  const [simulationResult, setSimulationResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const handleAddItem = () => {
    if ((itemId && itemName) || (!itemId && !itemName)) {
      setError("Please provide either Item ID or Item Name, not both");
      return;
    }

    if (itemId || itemName) {
      setItemsToBeUsed([...itemsToBeUsed, { itemId, name: itemName }]);
      setItemId("");
      setItemName("");
    }
  };

  const handleRemoveItem = (index) => {
    setItemsToBeUsed(items => items.filter((_, i) => i !== index));
  };

  const handleSimulate = async () => {
    if (!numOfDays && !toTimestamp) {
      setError("Please provide either number of days or target timestamp");
      return;
    }
    if (itemsToBeUsed.length === 0) {
      setError("Please add at least one item to simulate");
      return;
    }

    // Validate that each item has either itemId or name, not both
    const invalidItems = itemsToBeUsed.filter(item => item.itemId && item.name);
    if (invalidItems.length > 0) {
      setError("Each item should have either Item ID or Name, not both");
      return;
    }

    setError("");
    setLoading(true);
    try {
      const response = await simulateDays({
        numOfDays: numOfDays ? parseInt(numOfDays) : undefined,
        toTimestamp: toTimestamp || undefined,
        itemsToBeUsedPerDay: itemsToBeUsed,
      });

      if (response.success) {
        setSimulationResult(response);
      } else {
        setError(response.error || "Failed to simulate time");
      }
    } catch (error) {
      console.error("Error simulating time:", error);
      setError("Failed to connect to simulation service");
    }
    setLoading(false);
  };

  return (
    <div className="max-w-4xl mx-auto p-6">
      <div className="bg-white shadow-lg rounded-lg p-6">
        <h2 className="text-2xl font-bold text-gray-800 mb-6">Time Simulation</h2>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-6">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              Number of Days
            </label>
            <input
              type="number"
              min="1"
              value={numOfDays}
              onChange={(e) => {
                setNumOfDays(e.target.value);
                if (e.target.value) setToTimestamp("");
              }}
              className="w-full p-2 border rounded-md focus:ring-2 focus:ring-blue-500"
              placeholder="Enter number of days"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              Target Date/Time
            </label>
            <input
              type="datetime-local"
              value={toTimestamp}
              onChange={(e) => {
                setToTimestamp(e.target.value);
                if (e.target.value) setNumOfDays("");
              }}
              className="w-full p-2 border rounded-md focus:ring-2 focus:ring-blue-500"
            />
          </div>
        </div>

        <div className="mb-6">
          <label className="block text-sm font-medium text-gray-700 mb-2">
            Items to be Used Per Day
          </label>
          <div className="flex gap-2 mb-2">
            <input
              type="text"
              placeholder="Item ID"
              value={itemId}
              onChange={(e) => setItemId(e.target.value)}
              className="flex-1 p-2 border rounded-md focus:ring-2 focus:ring-blue-500"
            />
            <input
              type="text"
              placeholder="Item Name"
              value={itemName}
              onChange={(e) => setItemName(e.target.value)}
              className="flex-1 p-2 border rounded-md focus:ring-2 focus:ring-blue-500"
            />
            <button
              onClick={handleAddItem}
              className="bg-blue-500 hover:bg-blue-600 text-white px-4 py-2 rounded-md transition-colors"
            >
              Add Item
            </button>
          </div>

          {itemsToBeUsed.length > 0 && (
            <div className="mt-3 bg-gray-50 rounded-md p-3">
              <h4 className="text-sm font-medium text-gray-700 mb-2">Added Items:</h4>
              <ul className="space-y-1">
                {itemsToBeUsed.map((item, index) => (
                  <li
                    key={index}
                    className="flex items-center justify-between text-sm text-gray-600 bg-white p-2 rounded"
                  >
                    <span>{item.name || `Item ID: ${item.itemId}`}</span>
                    <button
                      onClick={() => handleRemoveItem(index)}
                      className="text-red-500 hover:text-red-600"
                    >
                      ✕
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>

        {error && (
          <div className="mb-4 p-3 bg-red-50 border border-red-200 text-red-600 rounded-md">
            {error}
          </div>
        )}

        <button
          onClick={handleSimulate}
          disabled={loading || (!numOfDays && !toTimestamp) || itemsToBeUsed.length === 0}
          className={`w-full p-3 rounded-lg text-white font-medium transition-colors ${
            loading || (!numOfDays && !toTimestamp) || itemsToBeUsed.length === 0
              ? "bg-gray-400 cursor-not-allowed"
              : "bg-green-500 hover:bg-green-600"
          }`}
        >
          {loading ? "Simulating..." : "Run Simulation"}
        </button>

        {simulationResult && (
          <div className="mt-6 bg-gray-50 rounded-lg p-4">
            <h3 className="text-lg font-semibold text-gray-800 mb-4">
              Simulation Results
            </h3>
            
            <div className="space-y-4">
              <div>
                <h4 className="font-medium text-gray-700 mb-2">New Date:</h4>
                <p className="text-gray-600">
                  {new Date(simulationResult.newDate).toLocaleString()}
                </p>
              </div>

              {simulationResult.changes.itemsUsed.length > 0 && (
                <div>
                  <h4 className="font-medium text-gray-700 mb-2">Items Used:</h4>
                  <ul className="bg-white rounded-md divide-y">
                    {simulationResult.changes.itemsUsed.map((item) => (
                      <li key={item.item_id} className="p-2 text-sm text-gray-600">
                        {item.name} - {item.remainingUses} uses remaining
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {simulationResult.changes.itemsExpired.length > 0 && (
                <div>
                  <h4 className="font-medium text-gray-700 mb-2">Expired Items:</h4>
                  <ul className="bg-white rounded-md divide-y">
                    {simulationResult.changes.itemsExpired.map((item) => (
                      <li key={item.item_id} className="p-2 text-sm text-gray-600">
                        {item.name}
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {simulationResult.changes.itemsDepletedToday.length > 0 && (
                <div>
                  <h4 className="font-medium text-gray-700 mb-2">Depleted Items:</h4>
                  <ul className="bg-white rounded-md divide-y">
                    {simulationResult.changes.itemsDepletedToday.map((item) => (
                      <li key={item.item_id} className="p-2 text-sm text-gray-600">
                        {item.name}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

export default TimeSimulation;