"""Parser regression checks using captured-shape text, without browser or email access."""
import ast
from collections import Counter
from pathlib import Path
import re
import tempfile
import unittest
from unittest.mock import MagicMock

source = ast.parse((Path(__file__).resolve().parents[1] / 'hpl.py').read_text())
functions = [node for node in source.body if isinstance(node, ast.FunctionDef) and node.name in ('normalize_lines', 'scrape_express_available', 'catalogue_records')]

class WatcherParserTests(unittest.TestCase):
    def scrape(self, text):
        with tempfile.TemporaryDirectory() as folder:
            namespace = {'re': re, 'Counter': Counter, 'BASE_DIR': Path(folder), 'TARGET_COLLECTION': 'Rec Pass Express', 'log': lambda message: None}
            exec(compile(ast.Module(body=functions, type_ignores=[]), 'watcher.py', 'exec'), namespace)
            page = MagicMock()
            page.locator.return_value.inner_text.return_value = text
            return namespace['scrape_express_available'](page, {'id':'rom','url':'https://example.invalid','short_name':'ROM'})

    def test_copy_counts_and_exact_collection(self):
        rows='Availability details\nAvailable (4)\nBarton\t\nRec Pass Express\n\tPASS ROM\tAvailable\nBarton\t\nRec Pass Express\n\tPASS ROM\tAvailable\nCentral\t\nRec Pass\n\tPASS ROM\tAvailable\nSaltfleet\t\nRec Pass Express\n\tPASS ROM\tAvailable\nNot available at this time (1)\nDundas\nRec Pass Express\nPASS ROM\tChecked out'
        self.assertEqual(self.scrape(rows),[{'name':'Barton','available':2},{'name':'Saltfleet','available':1}])

    def test_saltfleet_shelving_from_actual_hpl_output(self):
        rows = "Availability details\nHamilton Conservation Authority Pass\nPass\nAvailable (1)\nLocation\n\t\nCollection\n\t\nCall No.\n\t\nStatus\n\nSaltfleet\t\nRec Pass Express\n\tPASS HAM\tShelving\nNot available at this time (81)\nCentral\t\nRec Pass Express\n\tPASS HAM\tChecked Out"
        self.assertEqual(self.scrape(rows), [{'name':'Saltfleet','available':1,'shelving':1}])

    def test_mixed_statuses_at_one_branch(self):
        rows = "Availability details\nAvailable (2)\nBarton\t\nRec Pass Express\n\tPASS ROM\tAvailable\nBarton\t\nRec Pass Express\n\tPASS ROM\tShelving"
        self.assertEqual(self.scrape(rows), [{'name':'Barton','available':2,'shelving':1}])

    def test_catalogue_deduplicates_records_and_ignores_actions(self):
        namespace={'re':re}
        exec(compile(ast.Module(body=functions,type_ignores=[]),'hpl.py','exec'),namespace)
        links=[{'href':'/v2/record/S125C123','text':'Ontario Parks Pass'},
               {'href':'/v2/record/S125C123','text':'Add Ontario Parks Pass to shelf'},
               {'href':'/v2/record/S125C123','text':'Ontario Parks Pass'},
               {'href':'/v2/record/S125C456','text':'Art Gallery of Hamilton Pass'}]
        result=namespace['catalogue_records'](links)
        self.assertEqual(len(result),2)
        self.assertEqual(result[0]['name'],'Ontario Parks Pass')

    def test_confirmed_zero(self):
        self.assertEqual(self.scrape('Availability details\nAvailable (0)\nNot available at this time (8)'),[])

    def test_missing_heading_or_partial_row_fails(self):
        for text in ('Unavailable page', 'Availability details\nLoading…', 'Availability details\nAvailable (1)\nBarton\nRec Pass Express\nUnexpected layout'):
            with self.subTest(text=text), self.assertRaises(RuntimeError):
                self.scrape(text)

if __name__=='__main__': unittest.main()
