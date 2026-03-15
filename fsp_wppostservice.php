<?php

namespace FSPoster\App\Providers\WPPost;

use FSPoster\App\Models\Schedule;
use FSPoster\App\Providers\Core\Settings;
use FSPoster\App\Providers\Helpers\Helper;
use FSPoster\App\Providers\Schedules\ScheduleService;
use WP_Post;

class WPPostService
{

	private static $cacheWpEditedPosts = [];
	private static $cacheWpCreatedPosts = [];

    /**
     * WP Post edit edende bu event ishe dushur, DB update`den once. Bizde onu goturub cache edirik;
     * Bu eventin meqsedi onnan oteridir ki, WP-da programatiaclly/API ile post create edende, proses bele bash verir:
     *  1. DB-e postu insert edir
     *  2. set_object_terms edir (yeni bu eventi ishe salir ki, category/tag set eledim)
     *  3. Onnan sonra en sonda save_post eventini ishe salir.
     * Neticede programatically yaradilan postda save_post eventinden once set terms eventi ishe dushur,
     * ve o eventde ele bilir ki, bu post FS Poster install olmazdan once yaranmish postdu, ve bunu sadece user achib edit edib, term elave edib save edir;
     * bizde netice etibarile o post bizden once yarandigini dushunub onu paylashmirig, elave olarag fsp_enable_auto_share=0 olarag save edirik uzerine;
     * Neticede derhal sonra save_post eventi ishe dushse bele artig auto_share sonuludur deye post paylashilmir.
     * Ona gore bu cacheing sistemden istifade etmeli oldum. Editden once en birinci bu event ishe dushur, biz hemen POST id-ni save edirik ozumuzde ki, editdir bu.
     * Ve setObjectTerms-de eger edit deyilse postMutation`a buraxmirig ki, bu yeni yaranmish postdu ve save_post (oz original eventi) bunnan derhal sonra ishe dushecek zaten;
     *
     * @param $wpPostId
     * @param $wpPostData
     *
     * @return void
     */
	public static function postPreUpdated ( $wpPostId, $wpPostData ) {
		if ( defined( 'DOING_AUTOSAVE' ) && DOING_AUTOSAVE ) {
            return;
        }

		if ( wp_is_post_autosave( $wpPostId ) || wp_is_post_revision( $wpPostId ) ) {
            return;
        }

		self::$cacheWpEditedPosts[ $wpPostId ] = true;
	}

	/**
	 * Posta terms elave edildikde ve ya silindikde onu handle edir bu event.
	 * Chunki bizde chanellar termslere gore auto-sahre optionu deyishe bilir.
	 * Ona gore postu yarada yarada deyek ki, yeni term elave edib save edirse adam, bu halda chanellar yoxlanilir,
	 * eger gerek varsa yeni chanela uygun schedule yaradilir ve ya kohne chanelin schedulesi silinir.
	 *
	 * @param $wpPostId
	 * @param $terms
	 * @param $tt_ids
	 * @param $taxonomy
	 * @param $append
	 * @param $old_tt_ids
	 *
	 * @return void
	 */
	public static function setObjectTerms ( $wpPostId, $terms, $tt_ids, $taxonomy, $append, $old_tt_ids ) {
		if ( defined( 'DOING_AUTOSAVE' ) && DOING_AUTOSAVE ) {
            return;
        }

		if ( wp_is_post_autosave( $wpPostId ) || wp_is_post_revision( $wpPostId ) ) {
            return;
        }

		$termsUpdated = ! empty( array_diff( $old_tt_ids, $tt_ids ) ) || ! empty( array_diff( $tt_ids, $old_tt_ids ) );

        // Bele olmasinin sebebi: WordPress-de API ile (XML RPC or Rest API) post yaradanda, bismillah elememish bosh term set edir
        // Bir nov bosh ID-li post yaradir, ona Uncategorized set edir, sen API ile category gondersen bele bele edir;
        // Hetda XML RPC set term edende [] gonderir, amma Rest API [1] hansi ki, 1=Uncategorized
        // sonra save_post edib hemen ID-e data-ni set edir. ve sonra tezeden termleri set eden methodu xodduyum senin gonderdiyin termi yazir
        // Ashagidaki 2 deyishen ona goredi.
        // $isEditedAction - postun edit oldugunu cache edib saxlayir...
        // $cacheWpCreatedPosts - sirf rest api uchun yaradilib (xml rpc ferqli ishleyir). Rest API 1 resut ichinde createden sonra set term edir.
        $isEditAction = isset( self::$cacheWpEditedPosts[ $wpPostId ] );
        $isRestApiAndSettingTermsAfterPostCreation = isset( self::$cacheWpCreatedPosts[ $wpPostId ] );

		if( $termsUpdated && ($isEditAction || $isRestApiAndSettingTermsAfterPostCreation) )
		{
			$wpPost = get_post( $wpPostId );

			if ( ! empty( $wpPost ) ) {
                self::postMutation($wpPost, false, false, true);
            }
		}
	}

	/**
	 * Yeni post create edilende ve kohne posta save vuranda bu event ishe dushur.
	 * Amma biz burda yalniz yeni post yaradilan halini ele alacayig.
	 * Adeden WP-da manual olarag UI-dan yeni post yaradanda o auto-draft statusu ile dushur ve bu eventde handle edilmir zaten.
	 * Bu eventin esas rolu progamatically ve ya API ile yaradilan postlari handle etmekdir.
	 * Hansi ki, o postlar ele birbashe insert edilende publish, scheduled statuslari ile dushurler. (auto-draft yox)
	 *
	 * @param $wpPostId
	 * @param $wpPost
	 * @param $update
	 *
	 * @return void
	 */
	public static function postSaved ( $wpPostId, $wpPost, $update ) {
		if ( wp_is_post_revision( $wpPostId ) ) {
            return;
        }

		/* Bu event yalniz yeni yaradilan postlar uchundu. Edit olunan postlara postUpdated() methodu baxir */
		if( $update ) {
            return;
        }

		if($wpPost->post_status !== 'auto-draft') {
            self::postMutation($wpPost, true, true, false);
        }
	}

	/**
	 * Postda her hansi data deyishende bu event ishe dushur.
	 * Hem kohne postlari edit etdikde, meselen statusu future idi, draft eledi. ve ya post_date`i deyishdi ve s.
	 * Hem de manual olarag - UI`dan post yaradildigda da bu event bize yardim edir. Chunki UI-dan Add post clickledikde, WP avtomatik post insert edir DB-e;
	 * Statusunu auto-draft qoyur. Sonra user meselen title, description yazir ve s. save basir, bu halda cari event ishe dushur ki, statusu deyishdi:
	 * meselen statusu auto-draft -> publish oldu. Ve bizde onu goturub schedule yaradirig.
	 *
	 * @param $wpPostId
	 * @param $postAfter
	 * @param $postBefore
	 *
	 * @return void
	 */
	public static function postUpdated ( $wpPostId, $postAfter, $postBefore ) {
		if ( wp_is_post_revision( $wpPostId ) ) {
            return;
        }

		$postDateChanged   = $postBefore->post_date !== $postAfter->post_date;
		$postStatusChanged = ScheduleService::getScheduleStatusByWpPostStatus( $postBefore->post_status ) !== ScheduleService::getScheduleStatusByWpPostStatus( $postAfter->post_status );

		if ( $postStatusChanged || $postDateChanged ) {
            self::postMutation($postAfter, $postStatusChanged, $postDateChanged, false, $postBefore);
        }
	}

    public static function postMutation ( WP_Post $post, $postStatusChanged, $postDateChanged, $postTermsChanged, ?WP_Post $postBeforeMutation = null ) {
		if( ! $postStatusChanged && ! $postDateChanged && ! $postTermsChanged ) {
            return;
        }

        // if post created by FS Poster (calendar), then this hook is not needed
        if ( $post->post_type === 'fsp_post' ) {
            return;
        }

	    if ( !in_array( $post->post_status, [ 'publish', 'future', 'draft', 'pending', 'trash' ] ) ) {
            return;
        }

        // if post type is not whitelisted, just skip
        if ( !in_array($post->post_type, Settings::get('allowed_post_types', ['post', 'page', 'attachment', 'product']), true)) {
            return;
        }

	    $wpPostId = $post->ID;

	    if ( metadata_exists( 'post', $wpPostId, 'fsp_runned_for_this_post' ) ) {
            return;
        }

		$autoShareEnabledMetadataExists = metadata_exists( 'post', $wpPostId, 'fsp_enable_auto_share' );

	    if( $autoShareEnabledMetadataExists ) {
		    $autoShareOn = (bool) get_post_meta( $wpPostId, 'fsp_enable_auto_share', true );
	    }
	    /**
	     * FS Poster install olmazdan onceki postlari edit etdikde auto-share`i sondururuk ki, schedule yaranmasin
	     *
	     * $postTermsChanged - ona gore yoxlayir ki, yuxarida $autoShareEnabledMetadataExists yoxlayir. else if o demekdi ki, yuxaridaki shert false verib.
	     * Ve bu o demekdir ki, bura ya FS Posterden onceki postun editidir, ya da new post create edilir.
	     * Eger $postTermsChanged true olarsa new post ola bilmez. Chunki var olmayan bir postun termsleri deyishe bilmez zaten,
	     * birinci post yaranmalidiki termsi deyishe. Post yarananda da $autoShareEnabledMetadataExists exist olacag zaten;
	     * Ona gore o demeydi ki, bu editdir, amma FS Posterden onceki editdir ve bizim plugin onu edit olundu deye share ede bilmez.
	     */
		else if( $postTermsChanged || ($postBeforeMutation && $postBeforeMutation->post_status === 'publish') ) {
			$autoShareOn = false;
		}
		else {
			$autoShareOn = (bool) Settings::get( 'auto_share', true );
            self::$cacheWpCreatedPosts[$wpPostId] = true;
		}

	    $scheduleGroupId = get_post_meta( $wpPostId, 'fsp_schedule_group_id', true );

		if( ! empty( $scheduleGroupId ) ) {
			$schedulesCreatedByUserAction = get_post_meta( $wpPostId, 'fsp_schedule_created_manually', true );
			$needToRecreateSchedules = (! $schedulesCreatedByUserAction && $postTermsChanged) || ($postStatusChanged && ($post->post_status==='trash' || $postBeforeMutation->post_status==='trash'));
			$needToUpdateSchedulesDateAndStatus = $postStatusChanged || $postDateChanged;

			if( ! $autoShareOn && $post->post_status === 'publish' ) {
				ScheduleService::deleteScheduleCacheDataForWpPost( $wpPostId );
			}
			else if( $needToRecreateSchedules ) {
				ScheduleService::deleteSchedulesFromWpPost( $wpPostId, $scheduleGroupId );
				if ( $post->post_status !== 'trash' ) {
					ScheduleService::createSchedulesFromWpPost( $wpPostId, $scheduleGroupId );
				}
			}
			else if( $needToUpdateSchedulesDateAndStatus ) {
				ScheduleService::updateSchedulesStatusAndDeteFromWpPost( $wpPostId, $scheduleGroupId );
			}
		} else {
			if( $autoShareOn ) {
				$schedulesGroupId = ScheduleService::createSchedulesFromWpPost( $wpPostId );
				update_post_meta( $wpPostId, 'fsp_schedule_group_id', $schedulesGroupId );
			}

			/*
			 * Auto-share checkboxunun metasini yaradir. Ola biler ki, checkbox deyishdirilmeyibdi (enable/disable edilmeyib).
			 * Checkbox basilmayib deye Ajax requestde getmeyib backende ki, bu meta create edilsin.
			 * Ona gore de WP save hooknda default settingsdek durumu metaya yazdiririg.
			 * Hemchinin bu metadata FS Poster enabled oldugu zaman postun yarandigini, ve FS Posterin bu postu handle etdiyinin gostericisidir.
			*/
			update_post_meta( $wpPostId, 'fsp_enable_auto_share', $autoShareOn ? 1 : 0 );
		}
    }

    public static function deletePostSchedules ( $postId ) {
        Schedule::where( 'blog_id', Helper::getBlogId() )->where( 'wp_post_id', $postId )->delete();
    }

}