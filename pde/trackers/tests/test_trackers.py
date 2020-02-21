'''
.. codeauthor:: David Zwicker <david.zwicker@ds.mpg.de>
'''

import os
from unittest import mock

import numpy as np
import pytest

from .. import trackers
from ...grids import UnitGrid, CartesianGrid
from ...fields import ScalarField
from ...pdes import DiffusionPDE
from ...solvers import ExplicitSolver
from ...controller import Controller
from ...storage import MemoryStorage
from ...tools.misc import skipUnlessModule, module_available
        


@skipUnlessModule("matplotlib")
def test_plot_tracker(tmp_path):
    """ test whether the plot tracker creates files without errors """
    movie_file = tmp_path / "movie.mov"
    output_file = tmp_path / "img.png"
    output_folder = tmp_path / "folder/"
    output_folder.mkdir()
    
    grid = UnitGrid([4, 4])
    state = ScalarField.random_uniform(grid)
    pde = DiffusionPDE()
    tracker = trackers.PlotTracker(output_file=output_file,
                                   output_folder=output_folder,
                                   movie_file=movie_file,
                                   interval=0.1, show=False)
    
    pde.solve(state, t_range=0.5, dt=0.005, tracker=tracker, backend='numpy')
    
    assert output_file.exists()
    assert len(list(output_folder.iterdir())) == 6
    assert movie_file.exists()
    
    
    
def test_simple_progress():
    """ simple test for basic progress bar """
    pbar = trackers.ProgressTracker(interval=1)
    field = ScalarField(UnitGrid([3]))
    pbar.initialize(field)
    print(pbar.progress_bar.total)
    pbar.handle(field, 2)
    print(pbar.progress_bar.total)
    pbar.finalize()



def test_progress_no_tqdm(capsys):
    """ test progress bar without tqdm package """
    with mock.patch.dict('sys.modules', {'tqdm': None}):  # @UndefinedVariable
        with pytest.warns(UserWarning):
            test_simple_progress()
    captured = capsys.readouterr()
    assert len(captured.err) > 0



def test_trackers():
    """ test whether simple trackers can be used """
    times = []
    
    def store_time(state, t):
        times.append(t)
        
    def get_data(state):
        return {'integral': state.integral}
    
    devnull = open(os.devnull, 'w')
    data = trackers.DataTracker(get_data, interval=0.1)
    tracker_list = [trackers.PrintTracker(interval=0.1, stream=devnull),
                    trackers.CallbackTracker(store_time, interval=0.1),
                    data]
    if module_available("matplotlib"):
        tracker_list.append(trackers.PlotTracker(interval=0.1, show=False))
    
    grid = UnitGrid([16, 16])
    state = ScalarField.random_uniform(grid, 0.2, 0.3)
    pde = DiffusionPDE()
    pde.solve(state, t_range=1, dt=0.005, tracker=tracker_list)

    devnull.close()
    
    assert times == data.times
    if module_available("pandas"):
        df = data.dataframe
        np.testing.assert_allclose(df['time'], times)
        np.testing.assert_allclose(df['integral'], state.integral)


def test_callback_tracker():
    """ test trackers that support a callback """
    data = []
    
    def store_mean_data(state):
        data.append(state.average)
        
    def get_mean_data(state):
        return state.average
    
    grid = UnitGrid([4, 4])
    state = ScalarField.random_uniform(grid, 0.2, 0.3)
    pde = DiffusionPDE()
    data_tracker = trackers.DataTracker(get_mean_data, interval=0.1)
    tracker_list = [trackers.CallbackTracker(store_mean_data, interval=0.1),
                    data_tracker]
    pde.solve(state, t_range=0.5, dt=0.005, tracker=tracker_list,
              backend='numpy')
    
    np.testing.assert_array_equal(data, data_tracker.data)
   
    data = []
    
    def store_time(state, t):
        data.append(t)
        
    def get_time(state, t):
        return t
    
    grid = UnitGrid([4, 4])
    state = ScalarField.random_uniform(grid, 0.2, 0.3)
    pde = DiffusionPDE()
    data_tracker = trackers.DataTracker(get_time, interval=0.1)
    tracker_list = [trackers.CallbackTracker(store_time, interval=0.1),
                    data_tracker]
    pde.solve(state, t_range=0.5, dt=0.005, tracker=tracker_list,
              backend='numpy')
    
    ts = np.arange(0, 0.55, 0.1)
    np.testing.assert_allclose(data, ts, atol=1e-2)
    np.testing.assert_allclose(data_tracker.data, ts, atol=1e-2)
   
    
    
def test_steady_state_tracker():
    """ test the SteadyStateTracker """
    storage = MemoryStorage()
    c0 = ScalarField.random_uniform(UnitGrid([5]))
    pde = DiffusionPDE()
    tracker = trackers.SteadyStateTracker(atol=1e-2, rtol=1e-2)
    pde.solve(c0, 1e3, dt=0.1, tracker=[tracker, storage.tracker(interval=1e2)])
    assert len(storage) < 9  # finished early
    
    

def test_small_tracker_dt():
    """ test the case where the dt of the tracker is smaller than the dt 
    of the simulation """
    storage = MemoryStorage()
    pde = DiffusionPDE()
    c0 = ScalarField.random_uniform(UnitGrid([4, 4]), 0.1, 0.2)
    pde.solve(c0, 1e-2, dt=1e-3, method='explicit',
              tracker=storage.tracker(interval=1e-4))
    assert len(storage) == 11



def test_length_scale_tracker():
    """ test the LengthScaleTracker """
    g = CartesianGrid([[0, 2*np.pi]], 64, periodic=True)
    s = ScalarField.from_expression(g, 'sin(2 * x)')

    tracker = trackers.LengthScaleTracker(0.5)
    DiffusionPDE().solve(s, t_range=1e-2, dt=1e-3, tracker=tracker)
    np.testing.assert_allclose(tracker.length_scales, np.pi, rtol=1e-3)
    
    
    
def test_runtime_tracker():
    """ test the RuntimeTracker """
    s = ScalarField.random_uniform(UnitGrid([128]))
    tracker = trackers.RuntimeTracker('0:01')
    sol = ExplicitSolver(DiffusionPDE())
    con = Controller(sol, t_range=1e4, tracker=['progress', tracker])
    con.run(s, dt=1e-3)
    
    
    
def test_consistency_tracker():
    """ test the ConsistencyTracker """
    s = ScalarField.random_uniform(UnitGrid([128]))
    sol = ExplicitSolver(DiffusionPDE(1e3))
    con = Controller(sol, t_range=1e5, tracker=['consistency'])
    with np.errstate(all='ignore'):
        con.run(s, dt=1)
    assert con.info['t_final'] < con.info['t_end']