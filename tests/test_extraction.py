"""Extraction of structured fields from free-form breakdown messages.

Drivers type whatever they like, in Indonesian or English. Downstream reporting
needs columns, not prose. The rule that matters: a field the message does not
state must come back as None, never as a guess.
"""
import unittest

from dispatch.extract import extract_fault_report


class ExtractPlate(unittest.TestCase):
    def test_reads_indonesian_plate(self):
        r = extract_fault_report("Truck B1234XYZ pecah ban depan, tol Cikampek km 32")
        self.assertEqual(r['plate'], 'B1234XYZ')

    def test_reads_plate_without_spaces(self):
        r = extract_fault_report("Truck CA123456 blown front left tyre, N1 north km 43")
        self.assertEqual(r['plate'], 'CA123456')

    def test_missing_plate_is_none_not_guessed(self):
        r = extract_fault_report("ban bocor di tol dalam kota")
        self.assertIsNone(r['plate'])

    def test_does_not_mistake_road_code_for_plate(self):
        r = extract_fault_report("blown tyre on N1 north km 43")
        self.assertIsNone(r['plate'])


class ExtractLocation(unittest.TestCase):
    def test_reads_kilometre_marker(self):
        r = extract_fault_report("Truck B1234XYZ pecah ban depan, tol Cikampek km 32")
        self.assertEqual(r['km'], 32.0)

    def test_reads_decimal_kilometre(self):
        r = extract_fault_report("bocor ban, tol Jagorawi km 15.5")
        self.assertEqual(r['km'], 15.5)

    def test_reads_road_name(self):
        r = extract_fault_report("Truck B1234XYZ pecah ban depan, tol Cikampek km 32")
        self.assertEqual(r['road'], 'Tol Cikampek')

    def test_missing_km_is_none(self):
        r = extract_fault_report("ban bocor di tol Jagorawi")
        self.assertIsNone(r['km'])


class ExtractFault(unittest.TestCase):
    def test_classifies_tyre_fault_in_indonesian(self):
        r = extract_fault_report("Truck B1234XYZ pecah ban depan, tol Cikampek km 32")
        self.assertEqual(r['fault_type'], 'tyre')

    def test_classifies_tyre_fault_in_english(self):
        r = extract_fault_report("Truck CA123456 blown front left tyre, N1 north km 43")
        self.assertEqual(r['fault_type'], 'tyre')

    def test_classifies_battery_fault(self):
        r = extract_fault_report("aki soak tidak bisa starter, tol Jagorawi km 12")
        self.assertEqual(r['fault_type'], 'battery')

    def test_unknown_fault_is_none(self):
        r = extract_fault_report("tolong bantuan di km 20")
        self.assertIsNone(r['fault_type'])

    def test_reads_wheel_position(self):
        r = extract_fault_report("Truck B1234XYZ pecah ban depan, tol Cikampek km 32")
        self.assertEqual(r['position'], 'front')

    def test_reads_rear_position_indonesian(self):
        r = extract_fault_report("bocor ban belakang, tol Jagorawi km 15")
        self.assertEqual(r['position'], 'rear')


class ExtractLanguage(unittest.TestCase):
    def test_detects_indonesian(self):
        r = extract_fault_report("Truck B1234XYZ pecah ban depan, tol Cikampek km 32")
        self.assertEqual(r['language'], 'id')

    def test_detects_english(self):
        r = extract_fault_report("Truck CA123456 blown front left tyre, N1 north km 43")
        self.assertEqual(r['language'], 'en')

    def test_indonesian_words_outweigh_the_word_truck(self):
        # "Truck" is written by Indonesian drivers too, so one English-looking
        # token must not flip a sentence that is otherwise Indonesian.
        r = extract_fault_report("Truck D5566EF rem blong, jalan Pantura km 88")
        self.assertEqual(r['language'], 'id')


class ExtractContract(unittest.TestCase):
    def test_every_field_present_even_when_empty(self):
        r = extract_fault_report("halo")
        expected = {'plate', 'fault_type', 'position', 'road', 'km',
                    'language', 'raw_text', 'completeness'}
        self.assertEqual(set(r), expected)

    def test_keeps_original_text_for_audit(self):
        text = "Truck B1234XYZ pecah ban depan, tol Cikampek km 32"
        self.assertEqual(extract_fault_report(text)['raw_text'], text)

    def test_completeness_counts_only_filled_fields(self):
        full = extract_fault_report("Truck B1234XYZ pecah ban depan, tol Cikampek km 32")
        empty = extract_fault_report("halo")
        self.assertEqual(full['completeness'], 5)
        self.assertEqual(empty['completeness'], 0)

    def test_empty_message_does_not_raise(self):
        r = extract_fault_report("")
        self.assertIsNone(r['plate'])
        self.assertEqual(r['completeness'], 0)


if __name__ == '__main__':
    unittest.main()
