# Licensed under a 3-clause BSD style license - see LICENSE.rst
"""Model an instrument response for spectroscopic simulations.
"""
from __future__ import print_function, division

import math

import numpy as np

import astropy.constants
import astropy.units as u


class Instrument(object):
    """
    """
    def __init__(self, name, wavelength, fiber_acceptance, cameras,
                 primary_mirror_diameter, obscuration_diameter, support_width,
                 fiber_diameter, exposure_time):
        self.name = name
        self.wavelength = wavelength
        self.fiber_acceptance = fiber_acceptance
        self.cameras = cameras
        self.primary_mirror_diameter = primary_mirror_diameter
        self.obscuration_diameter = obscuration_diameter
        self.support_width = support_width
        self.fiber_diameter = fiber_diameter
        self.exposure_time = exposure_time

        # Calculate the geometric area.
        D = self.primary_mirror_diameter
        obs = self.obscuration_diameter
        support_area = 0.5*(D - obs) * self.support_width
        self.effective_area = (
            math.pi * ((0.5 * D) ** 2 - (0.5 * obs) ** 2) - 4 * support_area)

        # Calculate the fiber area.
        self.fiber_area = math.pi * (0.5 * self.fiber_diameter) ** 2

        # Calculate the energy per photon at each wavelength.
        hc = astropy.constants.h * astropy.constants.c
        energy_per_photon = (hc / self.wavelength).to(u.erg)

        # Calculate the rate of photons incident on the focal plane per
        # wavelength bin per unit spectral flux density. The fiber acceptance
        # fraction is not included in this calculation.
        wavelength_bin_size = np.gradient(self.wavelength)
        self.photons_per_bin = (
            self.effective_area * wavelength_bin_size / energy_per_photon
            ).to((u.cm**2 * u.Angstrom) / u.erg)


class Camera(object):
    """
    """
    def __init__(self, name, wavelength, throughput, angstroms_per_row,
                 fwhm_wave, neff_spatial, wavelength_min,
                 wavelength_max, read_noise, dark_current, gain):
        self.name = name
        self.wavelength = wavelength
        self.throughput = throughput
        self.angstroms_per_row = angstroms_per_row
        self.fwhm_wave = fwhm_wave
        self.neff_spatial = neff_spatial
        self.wavelength_min = wavelength_min
        self.wavelength_max = wavelength_max
        self.read_noise = read_noise
        self.dark_current = dark_current
        self.gain = gain

        # Calculate the RMS resolution assuming a Gaussian PSF.
        fwhm_to_sigma = 1. / (2 * math.sqrt(2 * math.log(2)))
        self.sigma_wave = fwhm_to_sigma * self.fwhm_wave

        # Calculate the size of each wavelength bin in units of pixel rows.
        wavelength_bin_size = np.gradient(self.wavelength)
        mask = self.angstroms_per_row.value > 0
        neff_wavelength = np.zeros_like(self.neff_spatial)
        neff_wavelength[mask] = (
            wavelength_bin_size[mask] / self.angstroms_per_row[mask])

        # Calculate the effective pixel area contributing to the signal
        # in each wavelength bin.
        self.neff_pixels = neff_wavelength * self.neff_spatial

        # Calculate the read noise per wavelength bin, assuming that
        # readnoise is uncorrelated between pixels (hence the sqrt scaling). The
        # value will be zero in pixels that are not used by this camera.
        self.read_noise_per_bin = (
            self.read_noise * np.sqrt(self.neff_pixels.to(u.pixel**2).value))

        # Calculate the dark current per wavelength bin.
        self.dark_current_per_bin = self.dark_current * self.neff_pixels


def initialize(config):
    """Initialize the instrument model from configuration parameters.

    Parameters
    ----------
    config : :class:`specsim.config.Configuration`
        The configuration parameters to use.

    Returns
    -------
    Instrument
        An initialized instrument model.
    """
    name = config.get('instrument.name').value
    cameras = config.get('instrument.cameras')
    camera_names = cameras.value.keys()
    initialized_cameras = []
    for camera_name in camera_names:
        camera = cameras.get(camera_name)
        psf = config.load_table(
            camera.get('psf'),
            ['angstroms_per_row', 'fwhm_wave', 'neff_spatial'])
        throughput = config.load_table(
            camera.get('throughput'), 'throughput')
        constants = config.get_constants(camera,
            ['wavelength_min', 'wavelength_max',
             'read_noise', 'dark_current', 'gain'])
        initialized_cameras.append(Camera(
            camera_name, config.wavelength, throughput,
            psf['angstroms_per_row'], psf['fwhm_wave'],
            psf['neff_spatial'], constants['wavelength_min'],
            constants['wavelength_max'], constants['read_noise'],
            constants['dark_current'], constants['gain']))

    constants = config.get_constants(
        config.get('instrument'),
        ['exposure_time', 'primary_mirror_diameter', 'obscuration_diameter',
         'support_width', 'fiber_diameter'])

    fiber_acceptance = config.load_table(
        config.get('instrument.fiberloss'), 'fiber_acceptance')

    instrument = Instrument(
        name, config.wavelength, fiber_acceptance, initialized_cameras,
        constants['primary_mirror_diameter'], constants['obscuration_diameter'],
        constants['support_width'], constants['fiber_diameter'],
        constants['exposure_time'])

    if config.verbose:
        print('Telescope effective area: {0}'.format(instrument.effective_area))
        print('Fiber entrance area: {0}'.format(instrument.fiber_area))

    return instrument
