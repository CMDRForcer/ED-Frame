"""October 2026 hull changes must preserve existing installed and planned slots."""
import json
import unittest
from pathlib import Path

from ed_companion.navigation.shipyard_finder import build_ship_catalog, module_fit_reference
from ed_companion.phase14.state_fleet import ship_slot_layout

DATA=Path(__file__).resolve().parents[1]/'ed_data'


class OctoberShipBalanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ships={r['symbol'].casefold():r for r in json.loads((DATA/'ships.json').read_text())}

    def test_extra_slots_preserve_old_names_and_add_only_the_announced_slot(self):
        expected={
            'type6':(6,{'Slot01_Size5':5,'Slot02_Size5':5,'Slot03_Size4':4,'Slot04_Size4':4,'Slot05_Size3':3,'Slot06_Size2':2,'Slot07_Size2':2,'Slot08_Size1':1,'PlanetaryApproachSuite':1}),
            'type7':(7,{'Slot01_Size6':6,'Slot02_Size6':6,'Slot03_Size5':6,'Slot04_Size5':5,'Slot05_Size4':5,'Slot06_Size4':5,'Slot07_Size2':3,'Slot08_Size2':3,'Slot09_Size2':2,'Slot09_Size1':1,'PlanetaryApproachSuite':1}),
            'empire_trader':(7,{'Slot01_Size7':7,'Slot02_Size6':6,'Slot03_Size4':4,'Slot04_Size4':4,'Slot05_Size3':3,'Slot06_Size3':3,'Slot07_Size2':2,'Slot08_Size2':2,'Slot09_Size1':1,'PlanetaryApproachSuite':1}),
            'federation_dropship':(6,{'Slot01_Size6':6,'Slot02_Size5':5,'Slot03_Size5':5,'Slot04_Size4':4,'Military01':4,'Military02':4,'Slot05_Size3':3,'Slot06_Size3':3,'Slot09_Size2':2,'Slot10_Size1':1,'PlanetaryApproachSuite':1}),
        }
        for symbol,(extra,old_sizes) in expected.items():
            with self.subTest(ship=symbol):
                ship=self.ships[symbol]
                physical={r['slot']:r for r in ship_slot_layout(ship,[],[])}
                self.assertEqual(len(ship['optional']),len(old_sizes)+1)
                self.assertEqual(physical[f'Slot00_Size{extra}']['slotSize'],extra)
                for slot,size in old_sizes.items():
                    self.assertEqual(physical[slot]['slotSize'],size)
                self.assertEqual(len(physical),len(ship_slot_layout(ship,[],[])))

    def test_partial_existing_wishlists_never_move_to_a_different_slot(self):
        cases={'type6':'Slot02_Size5','type7':'Slot02_Size6',
               'empire_trader':'Slot03_Size4','federation_dropship':'Slot02_Size5'}
        for symbol,slot in cases.items():
            with self.subTest(ship=symbol):
                installed={'slot':slot,'moduleId':'int_cargorack_size3_class1'}
                desired={slot:'int_cargorack_size4_class1'}
                rows=ship_slot_layout(self.ships[symbol],[installed],[],desired)
                planned=[r for r in rows if r['desiredModuleId']]
                self.assertEqual([r['slot'] for r in planned],[slot])
                self.assertEqual(planned[0]['desiredSourceSlot'],slot)
                self.assertEqual(planned[0]['moduleId'],installed['moduleId'])
                self.assertTrue(planned[0]['moduleChange'])
                self.assertTrue(next(r for r in rows if r['slot'].startswith('Slot00_'))['empty'])

    def test_new_utility_mount_and_larger_clipper_tank(self):
        scout=ship_slot_layout(self.ships['asp_scout'],[],[])
        self.assertEqual([r['slot'] for r in scout if r['group']=='UTILITY MOUNTS'],
                         ['TinyHardpoint1','TinyHardpoint2','TinyHardpoint3'])
        clipper=ship_slot_layout(self.ships['empire_trader'],[],[])
        self.assertEqual(next(r for r in clipper if r['slot']=='FuelTank')['slotSize'],5)

    def test_planetary_suite_uses_journal_name_and_retains_old_alias(self):
        for symbol in ('type6','type7','empire_trader','federation_dropship','asp_scout','explorer_nx'):
            ship=self.ships[symbol]
            spec=next(s for s in ship['optional'] if s.get('restriction')=='planetaryApproachSuite')
            module='int_planetapproachsuite'
            rows=ship_slot_layout(ship,[{'slot':'PlanetaryApproachSuite','moduleId':module}],[],
                                 {spec.get('legacyName','PlanetaryApproachSuite'):module})
            slot=next(r for r in rows if r['slot']=='PlanetaryApproachSuite')
            self.assertEqual(slot['moduleId'],module)
            self.assertEqual(slot['desiredModuleId'],module)

    def test_mass_changes_reach_fit_limits_and_reference_browser(self):
        expected={'asp_scout':140,'federation_dropship':500,'empire_trader':350,
                  'type7':300,'mandalay':190,'explorer_nx':825}
        reference=module_fit_reference()
        catalog={r['symbol']:r for r in build_ship_catalog(list(self.ships.values()))}
        for symbol,mass in expected.items():
            with self.subTest(ship=symbol):
                self.assertEqual(reference['ships'][symbol]['hullMass'],mass)
                self.assertEqual(catalog[symbol]['hullMass'],mass)

    def test_reference_speed_shields_and_heat_are_consistent(self):
        self.assertEqual((self.ships['asp_scout']['maximumSpeed'],self.ships['asp_scout']['boost']),(270,360))
        self.assertEqual((self.ships['viper_mkiv']['maximumSpeed'],self.ships['viper_mkiv']['boost']),(280,360))
        self.assertEqual(self.ships['federation_dropship']['maximumSpeed'],200)
        for symbol,shield in (('sidewinder',55),('eagle',80),('viper_mkiv',160),('type6',125),('empire_trader',200)):
            self.assertEqual(self.ships[symbol]['baseShieldStrength'],shield)
        self.assertEqual(self.ships['type7']['heatCapacity'],232)
        self.assertNotIn('minimumHeatDissipation',self.ships['type7']['flightReference'])

    def test_approximate_jump_reference_is_separate_from_operational_stats(self):
        for symbol,value in (('mandalay',95),('explorer_nx',90)):
            ship=self.ships[symbol]
            self.assertEqual(ship['referenceJumpRangeLy'],value)
            self.assertTrue(ship['referenceJumpRangeApproximate'])
            self.assertNotIn('jumpRange',ship)
            self.assertNotIn('MaxJumpRange',ship)

    def test_fit_reference_slot_counts_match_physical_catalog(self):
        reference=module_fit_reference()
        for symbol in ('type6','type7','empire_trader','federation_dropship','asp_scout'):
            ship=self.ships[symbol];slots=reference['ships'][symbol]['slots']
            self.assertEqual(len(slots['internal']),len(ship['optional']))
            self.assertEqual(slots['standard'][-1],ship['core']['fuelTank'])
            self.assertEqual(slots['hardpoints'].count(0),ship['utility'])

    def test_all_ships_have_unique_nonempty_physical_slots(self):
        for symbol,ship in self.ships.items():
            rows=ship_slot_layout(ship,[],[])
            self.assertEqual(len({r['slot'] for r in rows}),len(rows),symbol)
            self.assertTrue(all(r['slot'] for r in rows),symbol)


if __name__=='__main__':unittest.main()
