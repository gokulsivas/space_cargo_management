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

  const handleAddItem = () => {
    if (itemId || itemName) {
      setItemsToBeUsed([...itemsToBeUsed, { itemId, name: itemName }]);
      setItemId("");
      setItemName("");
    }
  };

  const handleSimulate = async () => {
    setLoading(true);
    try {
      const response = await simulateDays({
        numOfDays: numOfDays ? parseInt(numOfDays) : undefined,
        toTimestamp: toTimestamp || undefined,
        itemsToBeUsedPerDay: itemsToBeUsed,
      });
      setSimulationResult(response.data);
    } catch (error) {
      console.error("Error simulating time:", error);
    }
    setLoading(false);
  };

  return (
    <div className="flex">
        <div className="max-w-3xl mx-auto bg-white shadow-lg rounded-lg p-6">
          <h2 className="text-2xl font-bold text-gray-800 mb-4">Time Simulation</h2>

          <div className="mb-4">
            <label className="block text-gray-600">Number of Days:</label>
            <input
              type="number"
              value={numOfDays}
              onChange={(e) => setNumOfDays(e.target.value)}
              className="w-full p-2 border rounded"
            />
          </div>

          <div className="mb-4">
            <label className="block text-gray-600">To Timestamp (ISO):</label>
            <input
              type="datetime-local"
              value={toTimestamp}
              onChange={(e) => setToTimestamp(e.target.value)}
              className="w-full p-2 border rounded"
            />
          </div>

          <div className="mb-4">
            <label className="block text-gray-600">Items to be used per day:</label>
            <div className="flex gap-2">
              <input
                type="text"
                placeholder="Item ID"
                value={itemId}
                onChange={(e) => setItemId(e.target.value)}
                className="flex-1 p-2 border rounded"
              />
              <input
                type="text"
                placeholder="Item Name"
                value={itemName}
                onChange={(e) => setItemName(e.target.value)}
                className="flex-1 p-2 border rounded"
              />
              <button onClick={handleAddItem} className="bg-blue-500 text-white px-3 py-2 rounded">
                ➕ Add
              </button>
            </div>
            {itemsToBeUsed.length > 0 && (
              <ul className="mt-2 text-sm text-gray-700">
                {itemsToBeUsed.map((item, index) => (
                  <li key={index}>✔ {item.name || item.itemId}</li>
                ))}
              </ul>
            )}
          </div>

          <button
            onClick={handleSimulate}
            className="w-full bg-green-500 text-white p-3 rounded-lg disabled:opacity-50"
            disabled={loading}
          >
            {loading ? "Simulating..." : "Simulate Time"}
          </button>

          {simulationResult && (
            <div className="mt-6 p-4 bg-gray-100 rounded">
              <h3 className="text-lg font-semibold"> New Date: {simulationResult.newDate}</h3>
              <h4 className="mt-2 font-medium">Items Used:</h4>
              <ul>
                {simulationResult.changes.itemsUsed.map((item) => (
                  <li key={item.itemId}>{item.name} - {item.remainingUses} uses left</li>
                ))}
              </ul>
              <h4 className="mt-2 font-medium">Expired Items:</h4>
              <ul>
                {simulationResult.changes.itemsExpired.map((item) => (
                  <li key={item.itemId}>{item.name}</li>
                ))}
              </ul>
              <h4 className="mt-2 font-medium"> Depleted Items:</h4>
              <ul>
                {simulationResult.changes.itemsDepletedToday.map((item) => (
                  <li key={item.itemId}>{item.name}</li>
                ))}
              </ul>
            </div>
          )}
        </div>
      </div>
  );
};

export default TimeSimulation;
