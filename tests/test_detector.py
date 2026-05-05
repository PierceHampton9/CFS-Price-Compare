import unittest

from pc_pricer.detector import specs_from_raw


class DetectorTests(unittest.TestCase):
    def test_specs_from_raw_extracts_basic_fields(self):
        raw = {
            "ComputerSystem": {
                "Manufacturer": "LENOVO",
                "Model": "20XH001NUS",
                "PCSystemType": 3,
            },
            "ComputerSystemProduct": {
                "Vendor": "LENOVO",
                "Name": "ThinkPad X13 Yoga Gen 2",
                "SKUNumber": "20XH001NUS",
            },
            "SystemEnclosure": {
                "ChassisTypes": [31],
            },
            "Processor": {
                "Name": "Intel(R) Core(TM) i5-1135G7 @ 2.40GHz",
                "NumberOfCores": 4,
                "NumberOfLogicalProcessors": 8,
            },
            "PhysicalMemory": [
                {"Capacity": 8589934592},
                {"Capacity": 8589934592},
            ],
            "DiskDrive": [
                {"Model": "NVMe SAMSUNG MZVLQ512", "Size": 512110190592}
            ],
            "VideoController": [
                {"Name": "Intel(R) Iris(R) Xe Graphics"}
            ],
        }

        specs = specs_from_raw(raw)

        self.assertEqual(specs["brand"], "LENOVO")
        self.assertEqual(specs["model"], "ThinkPad X13 Yoga Gen 2")
        self.assertEqual(specs["oem_sku"], "20XH001NUS")
        self.assertEqual(specs["form_factor"], "laptop")
        self.assertEqual(specs["cpu_short"], "i5-1135G7")
        self.assertEqual(specs["ram_gb"], 16)
        self.assertEqual(specs["storage"][0]["type"], "SSD")


if __name__ == "__main__":
    unittest.main()
