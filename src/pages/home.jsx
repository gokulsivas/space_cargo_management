import { useEffect, useState } from "react";
import SideNavBar from "../components/dashboard/sideNavBar";
import { Card, CardContent, Typography, CircularProgress } from "@mui/material";
import { BarChart, Bar, PieChart, Pie, LineChart, Line, XAxis, YAxis, Tooltip, Legend, ResponsiveContainer } from "recharts";
import axios from "axios";

const Home = () => {
  const [cargoData, setCargoData] = useState([]);
  const [cargoArrivals, setCargoArrivals] = useState([]);
  const [weightTrends, setWeightTrends] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchData = async () => {
      try {
        const statusResponse = await axios.get("/api/cargo/status");
        setCargoData(statusResponse.data);

        const arrivalsResponse = await axios.get("/api/cargo/arrivals");
        setCargoArrivals(arrivalsResponse.data);

        const weightResponse = await axios.get("/api/cargo/weight-trends");
        setWeightTrends(weightResponse.data);
      } catch (error) {
        console.error("Error fetching data:", error);
      } finally {
        setLoading(false);
      }
    };

    fetchData();
  }, []);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-screen">
        <CircularProgress />
      </div>
    );
  }

  return (
    <div className="flex">
      <div className="hidden md:block md:w-64 bg-slate-50 h-screen fixed">
        <SideNavBar />
      </div>
      <div className="flex-1 p-6 ml-64">
        <div className="grid grid-cols-4 gap-4 mb-6">
          {cargoData.map((item) => (
            <Card key={item.status} className="p-4">
              <CardContent>
                <Typography variant="h6">{item.status}</Typography>
                <Typography variant="h4">{item.count}</Typography>
              </CardContent>
            </Card>
          ))}
        </div>

        <div className="grid grid-cols-2 gap-6">
          <div className="p-4 bg-white shadow-lg rounded-lg">
            <Typography variant="h6" className="mb-2">Cargo Status Distribution</Typography>
            <ResponsiveContainer width="100%" height={300}>
              <PieChart>
                <Pie data={cargoData} dataKey="count" nameKey="status" cx="50%" cy="50%" outerRadius={80} fill="#8884d8" label />
                <Tooltip />
              </PieChart>
            </ResponsiveContainer>
          </div>

          <div className="p-4 bg-white shadow-lg rounded-lg">
            <Typography variant="h6" className="mb-2">Monthly Cargo Arrivals</Typography>
            <ResponsiveContainer width="100%" height={300}>
              <BarChart data={cargoArrivals}>
                <XAxis dataKey="month" />
                <YAxis />
                <Tooltip />
                <Legend />
                <Bar dataKey="count" fill="#82ca9d" />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>

        <div className="mt-6 p-4 bg-white shadow-lg rounded-lg">
          <Typography variant="h6" className="mb-2">Cargo Weight Trends</Typography>
          <ResponsiveContainer width="100%" height={300}>
            <LineChart data={weightTrends}>
              <XAxis dataKey="month" />
              <YAxis />
              <Tooltip />
              <Legend />
              <Line type="monotone" dataKey="weight" stroke="#ff7300" />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </div>
    </div>
  );
};

export default Home;
