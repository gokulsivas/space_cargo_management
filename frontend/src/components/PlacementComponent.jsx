import { useState } from "react";
import { getPlacementRecommendations } from "../services/apiService";

const PlacementComponent = () => {
  const [items, setItems] = useState([]);
  const [containers, setContainers] = useState([]);
  const [placementData, setPlacementData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const [newItem, setNewItem] = useState({
    itemId: "",
    name: "",
    width: "",
    depth: "",
    height: "",
    priority: "",
    expiryDate: "",
    usageLimit: "",
    preferredZone: "",
  });

  const [newContainer, setNewContainer] = useState({
    containerId: "",
    zone: "",
    width: "",
    depth: "",
    height: "",
  });

  const addItem = () => {
    if (Object.values(newItem).some((val) => val === "")) {
      setError("All item fields are required.");
      return;
    }
    setItems([...items, newItem]);
    setNewItem({
      itemId: "",
      name: "",
      width: "",
      depth: "",
      height: "",
      priority: "",
      expiryDate: "",
      usageLimit: "",
      preferredZone: "",
    });
    setError(null);
  };

  const addContainer = () => {
    if (Object.values(newContainer).some((val) => val === "")) {
      setError("All container fields are required.");
      return;
    }
    setContainers([...containers, newContainer]);
    setNewContainer({
      containerId: "",
      zone: "",
      width: "",
      depth: "",
      height: "",
    });
    setError(null);
  };

  const fetchPlacement = async () => {
    if (items.length === 0 || containers.length === 0) {
      setError("At least one item and one container are required.");
      return;
    }

    setLoading(true);
    setError(null);

    try {
      const response = await getPlacementRecommendations({ items, containers });
      setPlacementData(response.data);
    } catch (error) {
      setError("Error fetching placement recommendations.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="max-w-4xl mx-auto p-6 bg-gray-100 shadow-md rounded-lg">
      <h2 className="text-2xl font-bold mb-4 text-center">Placement Recommendation System</h2>

      {error && <p className="text-red-600 text-center mb-4">{error}</p>}

      <div className="bg-white p-4 shadow-md rounded-lg mb-4">
        <h3 className="text-lg font-semibold mb-2">Add Item</h3>
        <div className="grid grid-cols-2 gap-3">
          {Object.keys(newItem).map((key) => (
            <div key={key}>
              <label className="block text-sm font-medium">{key.replace(/([A-Z])/g, " $1")}</label>
              <input
                type={key === "expiryDate" ? "date" : "text"}
                className="w-full p-2 border rounded-lg"
                value={newItem[key]}
                onChange={(e) => setNewItem({ ...newItem, [key]: e.target.value })}
              />
            </div>
          ))}
        </div>
        <button
          onClick={addItem}
          className="mt-4 w-full bg-blue-600 text-white py-2 rounded-lg hover:bg-blue-700"
        >
          Add Item
        </button>
      </div>

      <div className="bg-white p-4 shadow-md rounded-lg mb-4">
        <h3 className="text-lg font-semibold mb-2">Add Container</h3>
        <div className="grid grid-cols-2 gap-3">
          {Object.keys(newContainer).map((key) => (
            <div key={key}>
              <label className="block text-sm font-medium">{key.replace(/([A-Z])/g, " $1")}</label>
              <input
                type="text"
                className="w-full p-2 border rounded-lg"
                value={newContainer[key]}
                onChange={(e) => setNewContainer({ ...newContainer, [key]: e.target.value })}
              />
            </div>
          ))}
        </div>
        <button
          onClick={addContainer}
          className="mt-4 w-full bg-green-600 text-white py-2 rounded-lg hover:bg-green-700"
        >
          Add Container
        </button>
      </div>

      <div className="grid grid-cols-2 gap-4">
        <div className="bg-white p-4 shadow-md rounded-lg">
          <h3 className="text-lg font-semibold mb-2">Added Items</h3>
          {items.length === 0 ? (
            <p className="text-gray-500">No items added.</p>
          ) : (
            <pre className="text-sm bg-gray-200 p-2 rounded-lg">{JSON.stringify(items, null, 2)}</pre>
          )}
        </div>

        <div className="bg-white p-4 shadow-md rounded-lg">
          <h3 className="text-lg font-semibold mb-2">Added Containers</h3>
          {containers.length === 0 ? (
            <p className="text-gray-500">No containers added.</p>
          ) : (
            <pre className="text-sm bg-gray-200 p-2 rounded-lg">{JSON.stringify(containers, null, 2)}</pre>
          )}
        </div>
      </div>

      <button
        onClick={fetchPlacement}
        className="mt-4 w-full bg-purple-600 text-white py-3 rounded-lg hover:bg-purple-700"
        disabled={loading}
      >
        {loading ? "Loading..." : "Get Placement Recommendations"}
      </button>

      {placementData && (
        <div className="mt-6 bg-white p-4 shadow-md rounded-lg">
          <h3 className="text-lg font-semibold mb-2">Placement Recommendations</h3>
          <pre className="text-sm bg-gray-200 p-2 rounded-lg">{JSON.stringify(placementData, null, 2)}</pre>
        </div>
      )}
    </div>
  );
};

export default PlacementComponent;
