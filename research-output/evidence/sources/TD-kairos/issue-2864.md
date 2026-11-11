# kairos-io/kairos#2864: Implement systemd-boot boot assessment
state: closed created: 2024-09-17T09:47:21Z closed: 2024-11-27T10:25:35Z

systemd-boot has a was to perform boot assessment and fallback to other entries if booting fails. It is described in detail [here](https://uapi-group.org/specifications/specs/boot_loader_specification/#boot-counting) and [here](https://systemd.io/AUTOMATIC_BOOT_ASSESSMENT/). It's not very complicated and only requires us to name the conf/efi files in a certain way and also make sure we [order](https://uapi-group.org/specifications/specs/boot_loader_specification/#sorting) entries properly (so that the right one is picked as a fallback).


Note:
Originally investigated while [documenting](https://github.com/kairos-io/kairos/issues/2798#issuecomment-2355029574) how Kairos does boot assessment, 
